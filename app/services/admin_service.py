"""Admin business logic.

Two functions use the filesystem directly (no DB required).
All remaining functions issue SQLAlchemy async queries against
the architecture_ai database.
"""
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy import Float, case, delete as sa_delete, func, select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.admin_models import (
    AgentListResponse,
    AgentStatsView,
    DeleteFileResponse,
    DeleteImageResponse,
    DeleteProjectResponse,
    FileInfo,
    FileListResponse,
    FileTypeBreakdown,
    ImageAdminView,
    ImageListResponse,
    ImageSummary,
    ProjectAdminView,
    ProjectDetailResponse,
    ProjectListResponse,
    ProjectRenameResponse,
    SystemLogListResponse,
    SystemLogView,
    SystemStatsResponse,
    UserAdminView,
    UserListResponse,
    UserStatusResponse,
)
from app.models.orm_models import (
    Agent,
    AgentRun,
    BuildingStyleResult,
    Image,
    Project,
    Role,
    SystemLog,
    User,
)
from app.services.analysis_detail import build_detail_payload
from app.services.project_service import (
    delete_project as delete_project_rows,
    unlink_upload_file,
    upload_file_by_id,
)
from app.services.system_log_service import LEVEL_INFO, log_event
from app.utils.helpers import format_file_size


# ── Filesystem (live, no DB) ──────────────────────────────────────────────────

def get_system_stats() -> SystemStatsResponse:
    """Scan the upload directory and return file-count and size statistics."""
    upload_path = Path(settings.UPLOAD_DIR)
    if not upload_path.exists():
        return SystemStatsResponse(
            total_files=0,
            total_size_bytes=0,
            total_size_human="0.00 B",
            upload_dir=settings.UPLOAD_DIR,
            breakdown_by_type=[],
        )

    ext_stats: Dict[str, Dict[str, int]] = {}
    total_size = 0

    for entry in upload_path.iterdir():
        if not entry.is_file():
            continue
        size = entry.stat().st_size
        ext = entry.suffix.lstrip(".").lower() or "unknown"
        total_size += size
        if ext not in ext_stats:
            ext_stats[ext] = {"count": 0, "total_size_bytes": 0}
        ext_stats[ext]["count"] += 1
        ext_stats[ext]["total_size_bytes"] += size

    breakdown: List[FileTypeBreakdown] = [
        FileTypeBreakdown(
            extension=ext,
            count=stats["count"],
            total_size_bytes=stats["total_size_bytes"],
            total_size_human=format_file_size(stats["total_size_bytes"]),
        )
        for ext, stats in sorted(ext_stats.items())
    ]

    return SystemStatsResponse(
        total_files=sum(b.count for b in breakdown),
        total_size_bytes=total_size,
        total_size_human=format_file_size(total_size) if total_size else "0.00 B",
        upload_dir=settings.UPLOAD_DIR,
        breakdown_by_type=breakdown,
    )


def list_upload_files() -> FileListResponse:
    """List every file in the upload directory, sorted newest-first by mtime."""
    upload_path = Path(settings.UPLOAD_DIR)
    if not upload_path.exists():
        return FileListResponse(total=0, files=[])

    files: List[FileInfo] = []
    for entry in upload_path.iterdir():
        if not entry.is_file():
            continue
        stat = entry.stat()
        ext = entry.suffix.lstrip(".").lower()
        files.append(
            FileInfo(
                file_id=entry.stem,
                filename=entry.name,
                extension=ext,
                size_bytes=stat.st_size,
                size_human=format_file_size(stat.st_size),
                modified_at=datetime.fromtimestamp(stat.st_mtime),
            )
        )

    files.sort(key=lambda f: f.modified_at, reverse=True)
    return FileListResponse(total=len(files), files=files)


# ── DB-backed admin endpoints ────────────────────────────────────────────────

async def list_users(db: AsyncSession) -> UserListResponse:
    """Return every user joined with the role name from the Roles table."""
    result = await db.execute(
        select(User, Role.RoleName)
        .join(Role, User.RoleId == Role.RoleId)
        .order_by(User.CreatedAt.desc())
    )
    rows = result.all()
    users = [
        UserAdminView(
            user_id=user.UserId,
            email=user.Email,
            name=user.Name,
            picture=user.Picture,
            is_active=user.IsActive,
            role_name=role_name,
            created_at=user.CreatedAt,
        )
        for user, role_name in rows
    ]
    return UserListResponse(users=users, total=len(users))


async def update_user_status(
    db: AsyncSession, user_id: str, is_active: bool
) -> UserStatusResponse:
    """Toggle the IsActive flag on a single user account.

    Admin accounts are protected: attempting to deactivate one returns 400.
    Records the change in the audit log.

    Raises:
        HTTPException 404: If the user does not exist.
        HTTPException 400: If the target user holds the admin role.
    """
    lookup = await db.execute(
        select(User.Email, Role.RoleName)
        .join(Role, User.RoleId == Role.RoleId)
        .where(User.UserId == user_id)
    )
    row = lookup.first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )
    email, role_name = row
    if role_name == "admin" and not is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Không thể vô hiệu hóa tài khoản admin",
        )

    await db.execute(
        sa_update(User)
        .where(User.UserId == user_id)
        .values(IsActive=is_active, UpdatedAt=datetime.now(timezone.utc))
    )
    await db.commit()

    action = "activated" if is_active else "deactivated"
    await log_event(db, LEVEL_INFO, f"Admin {action} account: {email}")
    return UserStatusResponse(user_id=user_id, is_active=is_active)


async def list_projects(db: AsyncSession) -> ProjectListResponse:
    """Return every project across all users, newest-first.

    Joins ``User`` so each project carries its owner's name/email instead of
    only the raw UUID (admins need to see who owns a project at a glance).
    """
    result = await db.execute(
        select(Project, User.Name, User.Email)
        .outerjoin(User, Project.UserId == User.UserId)
        .order_by(Project.CreatedAt.desc())
    )
    projects = [
        ProjectAdminView(
            project_id=p.ProjectId,
            user_id=p.UserId,
            user_name=user_name,
            user_email=user_email,
            project_name=p.ProjectName,
            description=p.Description,
            created_at=p.CreatedAt,
        )
        for p, user_name, user_email in result.all()
    ]
    return ProjectListResponse(projects=projects, total=len(projects))


async def get_project_detail(db: AsyncSession, project_id: str) -> ProjectDetailResponse:
    """Return a single project plus a summary of all its images.

    Raises:
        HTTPException 404: If the project does not exist.
    """
    proj_result = await db.execute(select(Project).where(Project.ProjectId == project_id))
    project = proj_result.scalar_one_or_none()
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )

    img_result = await db.execute(
        select(Image, BuildingStyleResult)
        .outerjoin(BuildingStyleResult, Image.ImageId == BuildingStyleResult.ImageId)
        .where(Image.ProjectId == project_id)
        .order_by(Image.UploadedAt.desc())
    )
    images = [
        ImageSummary(
            image_id=img.ImageId,
            image_path=img.ImagePath,
            analysis_status=img.AnalysisStatus,
            uploaded_at=img.UploadedAt,
            style=bsr.FinalStyle if bsr else None,
            confidence=bsr.Confidence if bsr else None,
        )
        for img, bsr in img_result.all()
    ]
    return ProjectDetailResponse(
        project_id=project.ProjectId,
        user_id=project.UserId,
        project_name=project.ProjectName,
        description=project.Description,
        created_at=project.CreatedAt,
        images=images,
        total_images=len(images),
    )


async def rename_project(
    db: AsyncSession, project_id: str, new_name: str
) -> ProjectRenameResponse:
    """Rename a project; record the change in the audit log.

    Raises:
        HTTPException 400: If the new name is blank.
        HTTPException 404: If the project does not exist.
    """
    clean_name = (new_name or "").strip()
    if not clean_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tên dự án không được để trống",
        )

    result = await db.execute(
        sa_update(Project)
        .where(Project.ProjectId == project_id)
        .values(ProjectName=clean_name)
    )
    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )
    await db.commit()
    await log_event(db, LEVEL_INFO, f"Admin renamed project {project_id} -> {clean_name}")
    return ProjectRenameResponse(project_id=project_id, project_name=clean_name)


async def delete_project(db: AsyncSession, project_id: str) -> DeleteProjectResponse:
    """Delete a project by id (admin); record the deletion in the audit log.

    The cascade + physical-file cleanup lives in ``project_service`` so the admin
    tools and a user deleting their own account share one implementation.
    """
    deleted = await delete_project_rows(db, project_id)
    if deleted:
        await log_event(db, LEVEL_INFO, f"Admin deleted project: {project_id}")
    return DeleteProjectResponse(project_id=project_id, deleted=deleted)


async def list_images(db: AsyncSession) -> ImageListResponse:
    """Return every image across all projects, newest-first."""
    result = await db.execute(select(Image).order_by(Image.UploadedAt.desc()))
    images = [
        ImageAdminView(
            image_id=img.ImageId,
            project_id=img.ProjectId,
            image_path=img.ImagePath,
            analysis_status=img.AnalysisStatus,
            error_message=img.ErrorMessage,
            uploaded_at=img.UploadedAt,
        )
        for img in result.scalars().all()
    ]
    return ImageListResponse(images=images, total=len(images))


async def get_image_detail(db: AsyncSession, image_id: str) -> Dict[str, Any]:
    """Return the full stored analysis for any image (admin, not owner-scoped).

    Reads ``BuildingStyleResults.DetailJson`` when present, else builds a summary.

    Raises:
        HTTPException 404: If the image does not exist.
    """
    result = await db.execute(
        select(Image, BuildingStyleResult)
        .outerjoin(BuildingStyleResult, Image.ImageId == BuildingStyleResult.ImageId)
        .where(Image.ImageId == image_id)
    )
    row = result.first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Image {image_id} not found",
        )
    img, bsr = row
    return build_detail_payload(image_id, img, bsr)


async def resolve_image_file_path(db: AsyncSession, image_id: str) -> Path:
    """Return the on-disk path of an image's original file (admin, any owner).

    Raises:
        HTTPException 404: If the image row or its file is missing.
    """
    result = await db.execute(select(Image.ImagePath).where(Image.ImageId == image_id))
    image_path = result.scalar_one_or_none()
    if image_path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Image {image_id} not found",
        )
    path = Path(image_path)
    if not path.is_file():
        # Fall back to the upload dir by file-id stem (path may have moved).
        path = upload_file_by_id(path.stem)
    return path


async def delete_image(db: AsyncSession, image_id: str) -> DeleteImageResponse:
    """Delete an image by id; FK CASCADE removes Components and analysis rows.

    The physical image file is also unlinked so deleting an analysis cleans up
    its asset (the file the User-facing image endpoint serves).
    """
    # Resolve the file-id BEFORE deleting the row.
    path_result = await db.execute(
        select(Image.ImagePath).where(Image.ImageId == image_id)
    )
    image_path = path_result.scalar_one_or_none()

    result = await db.execute(sa_delete(Image).where(Image.ImageId == image_id))
    await db.commit()
    deleted = result.rowcount > 0
    if deleted:
        if image_path:
            unlink_upload_file(Path(image_path).stem)
        await log_event(db, LEVEL_INFO, f"Admin deleted image: {image_id}")
    return DeleteImageResponse(image_id=image_id, deleted=deleted)


def resolve_upload_file_path(file_id: str) -> Path:
    """Return the on-disk path for a raw upload file by its file-id."""
    return upload_file_by_id(file_id)


async def delete_upload_file(db: AsyncSession, file_id: str) -> DeleteFileResponse:
    """Delete a physical upload file, but only if it is NOT linked to an analysis.

    A file referenced by an Image row is the asset of a stored analysis; deleting
    it directly would leave the analysis with a missing image. Such files must be
    removed by deleting the analysis (which unlinks the file). Only orphan files
    (no Image references them) may be deleted here.

    Returns ``deleted=False`` (rather than 404) when the file is already gone,
    so the UI converges to the desired state idempotently.

    Raises:
        HTTPException 409: If the file is still linked to an analysis.
    """
    paths_result = await db.execute(select(Image.ImagePath))
    referenced = {Path(p).stem for p in paths_result.scalars().all() if p}
    if file_id in referenced:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Tệp đang được dùng bởi một phân tích — hãy xóa phân tích đó "
                "ở tab Phân Tích (việc xóa phân tích sẽ tự dọn tệp này)."
            ),
        )

    deleted = unlink_upload_file(file_id)
    if deleted:
        await log_event(db, LEVEL_INFO, f"Admin deleted file: {file_id}")
    return DeleteFileResponse(file_id=file_id, deleted=deleted)


async def list_system_logs(
    db: AsyncSession, limit: int = 100, level: Optional[str] = None
) -> SystemLogListResponse:
    """Return the most recent system log entries (capped by limit).

    Args:
        level: Optional level filter (e.g. ``INFO`` / ``WARNING`` / ``ERROR``).
    """
    query = select(SystemLog)
    if level:
        query = query.where(SystemLog.LogLevel == level.upper())
    query = query.order_by(SystemLog.CreatedAt.desc()).limit(limit)

    result = await db.execute(query)
    logs = [
        SystemLogView(
            log_id=row.LogId,
            log_level=row.LogLevel,
            message=row.Message,
            created_at=row.CreatedAt,
        )
        for row in result.scalars().all()
    ]
    return SystemLogListResponse(logs=logs, total=len(logs))


async def list_agents(db: AsyncSession) -> AgentListResponse:
    """Return all pipeline agents with aggregated run statistics."""
    result = await db.execute(
        select(
            Agent.AgentId,
            Agent.AgentName,
            Agent.Description,
            func.count(AgentRun.RunId).label("total_runs"),
            func.sum(case((AgentRun.ParseSuccess == True, 1), else_=0)).label(  # noqa: E712
                "successful_runs"
            ),
            func.avg(func.cast(AgentRun.LatencyMs, Float)).label("avg_latency_ms"),
        )
        .outerjoin(AgentRun, Agent.AgentId == AgentRun.AgentId)
        .group_by(Agent.AgentId, Agent.AgentName, Agent.Description)
        .order_by(Agent.AgentName)
    )
    rows = result.all()

    agents: List[AgentStatsView] = []
    for row in rows:
        total_runs = int(row.total_runs or 0)
        successful = int(row.successful_runs or 0)
        success_rate = (successful / total_runs) if total_runs > 0 else 0.0
        avg_latency = float(row.avg_latency_ms or 0.0)
        agents.append(
            AgentStatsView(
                agent_id=row.AgentId,
                agent_name=row.AgentName,
                description=row.Description,
                total_runs=total_runs,
                success_rate=success_rate,
                avg_latency_ms=avg_latency,
            )
        )

    return AgentListResponse(agents=agents, total=len(agents))

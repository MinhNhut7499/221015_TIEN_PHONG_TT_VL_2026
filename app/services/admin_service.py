"""Admin business logic.

Two functions use the filesystem directly (no DB required).
All remaining functions issue SQLAlchemy async queries against
the architecture_ai database.
"""
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from fastapi import HTTPException, status
from sqlalchemy import Float, case, delete as sa_delete, func, select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.admin_models import (
    AgentListResponse,
    AgentStatsView,
    DeleteImageResponse,
    DeleteProjectResponse,
    FileInfo,
    FileListResponse,
    FileTypeBreakdown,
    ImageAdminView,
    ImageListResponse,
    ProjectAdminView,
    ProjectListResponse,
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
    Image,
    Project,
    Role,
    SystemLog,
    User,
)
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
    """Toggle the IsActive flag on a single user account."""
    result = await db.execute(
        sa_update(User)
        .where(User.UserId == user_id)
        .values(IsActive=is_active, UpdatedAt=datetime.now(timezone.utc))
    )
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )
    return UserStatusResponse(user_id=user_id, is_active=is_active)


async def list_projects(db: AsyncSession) -> ProjectListResponse:
    """Return every project across all users, newest-first."""
    result = await db.execute(select(Project).order_by(Project.CreatedAt.desc()))
    projects = [
        ProjectAdminView(
            project_id=p.ProjectId,
            user_id=p.UserId,
            project_name=p.ProjectName,
            description=p.Description,
            created_at=p.CreatedAt,
        )
        for p in result.scalars().all()
    ]
    return ProjectListResponse(projects=projects, total=len(projects))


async def delete_project(db: AsyncSession, project_id: str) -> DeleteProjectResponse:
    """Delete a project by id; FK CASCADE removes Images and downstream rows."""
    result = await db.execute(
        sa_delete(Project).where(Project.ProjectId == project_id)
    )
    await db.commit()
    return DeleteProjectResponse(project_id=project_id, deleted=result.rowcount > 0)


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


async def delete_image(db: AsyncSession, image_id: str) -> DeleteImageResponse:
    """Delete an image by id; FK CASCADE removes Components and analysis rows."""
    result = await db.execute(sa_delete(Image).where(Image.ImageId == image_id))
    await db.commit()
    return DeleteImageResponse(image_id=image_id, deleted=result.rowcount > 0)


async def list_system_logs(
    db: AsyncSession, limit: int = 100
) -> SystemLogListResponse:
    """Return the most recent system log entries (capped by limit)."""
    result = await db.execute(
        select(SystemLog).order_by(SystemLog.CreatedAt.desc()).limit(limit)
    )
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

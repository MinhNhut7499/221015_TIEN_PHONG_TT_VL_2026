"""Admin router — 10 protected endpoints.

All handlers require admin privileges via ``require_admin``.
Handlers are thin orchestrators: they call the service layer and
return the result directly — no business logic in this file.
"""
from typing import Annotated, Any, Dict, Optional

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import require_admin
from app.models.admin_models import (
    AgentListResponse,
    DeleteFileResponse,
    DeleteImageResponse,
    DeleteProjectResponse,
    FileListResponse,
    ImageListResponse,
    ProjectDetailResponse,
    ProjectListResponse,
    ProjectRenameRequest,
    ProjectRenameResponse,
    SystemLogListResponse,
    SystemStatsResponse,
    UserListResponse,
    UserStatusResponse,
    UserStatusUpdate,
)
from app.services import admin_service

router = APIRouter()

# Shorthand type alias — injects require_admin and discards the returned payload
# (callers only need the side-effect: 403 if not admin).
_Admin = Annotated[Dict[str, Any], Depends(require_admin)]
_DB = Annotated[AsyncSession, Depends(get_db)]


# ── Filesystem ─────────────────────────────────────────────────────────────────

@router.get(
    "/stats",
    response_model=SystemStatsResponse,
    summary="Upload directory statistics",
)
async def get_stats(_: _Admin) -> SystemStatsResponse:
    """Return total file count, total size, and per-extension breakdown."""
    return admin_service.get_system_stats()


@router.get(
    "/files",
    response_model=FileListResponse,
    summary="List uploaded files",
)
async def list_files(_: _Admin) -> FileListResponse:
    """List every file in the upload directory, sorted newest-first."""
    return admin_service.list_upload_files()


@router.get(
    "/files/{file_id}/raw",
    summary="Serve a raw uploaded file",
)
async def serve_file(file_id: str, _: _Admin) -> FileResponse:
    """Stream the bytes of an uploaded file by its file-id (admin preview)."""
    return FileResponse(str(admin_service.resolve_upload_file_path(file_id)))


@router.delete(
    "/files/{file_id}",
    response_model=DeleteFileResponse,
    summary="Delete an uploaded file from disk",
)
async def delete_file(file_id: str, _: _Admin, db: _DB) -> DeleteFileResponse:
    """Delete a physical file from the upload directory."""
    return await admin_service.delete_upload_file(db, file_id)


# ── Users ──────────────────────────────────────────────────────────────────────

@router.get(
    "/users",
    response_model=UserListResponse,
    summary="List all users",
)
async def list_users(_: _Admin, db: _DB) -> UserListResponse:
    """Return all registered users with their role (Users JOIN Roles)."""
    return await admin_service.list_users(db)


@router.patch(
    "/users/{user_id}/status",
    response_model=UserStatusResponse,
    summary="Activate or deactivate a user",
)
async def update_user_status(
    user_id: str,
    body: UserStatusUpdate,
    _: _Admin,
    db: _DB,
) -> UserStatusResponse:
    """Toggle the IsActive flag on a user account."""
    return await admin_service.update_user_status(db, user_id, body.is_active)


# ── Projects ───────────────────────────────────────────────────────────────────

@router.get(
    "/projects",
    response_model=ProjectListResponse,
    summary="List all projects",
)
async def list_projects(_: _Admin, db: _DB) -> ProjectListResponse:
    """Return all projects across all users."""
    return await admin_service.list_projects(db)


@router.get(
    "/projects/{project_id}",
    response_model=ProjectDetailResponse,
    summary="Get a project with its images",
)
async def get_project_detail(project_id: str, _: _Admin, db: _DB) -> ProjectDetailResponse:
    """Return a single project plus a summary of all its images."""
    return await admin_service.get_project_detail(db, project_id)


@router.patch(
    "/projects/{project_id}/name",
    response_model=ProjectRenameResponse,
    summary="Rename a project",
)
async def rename_project(
    project_id: str,
    body: ProjectRenameRequest,
    _: _Admin,
    db: _DB,
) -> ProjectRenameResponse:
    """Update a project's display name."""
    return await admin_service.rename_project(db, project_id, body.project_name)


@router.delete(
    "/projects/{project_id}",
    response_model=DeleteProjectResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete a project",
)
async def delete_project(project_id: str, _: _Admin, db: _DB) -> DeleteProjectResponse:
    """Delete a project; DB FK cascade removes all child records."""
    return await admin_service.delete_project(db, project_id)


# ── Images ─────────────────────────────────────────────────────────────────────

@router.get(
    "/images",
    response_model=ImageListResponse,
    summary="List all images",
)
async def list_images(_: _Admin, db: _DB) -> ImageListResponse:
    """Return all uploaded images across all projects."""
    return await admin_service.list_images(db)


@router.get(
    "/images/{image_id}",
    summary="Get the full stored analysis of an image",
)
async def get_image_detail(image_id: str, _: _Admin, db: _DB) -> Dict[str, Any]:
    """Return the full stored analysis (DetailJson) or a summary for any image."""
    return await admin_service.get_image_detail(db, image_id)


@router.get(
    "/images/{image_id}/raw",
    summary="Serve the original image file of an analysis",
)
async def serve_image(image_id: str, _: _Admin, db: _DB) -> FileResponse:
    """Stream the original uploaded image for any analysis (admin preview)."""
    return FileResponse(str(await admin_service.resolve_image_file_path(db, image_id)))


@router.delete(
    "/images/{image_id}",
    response_model=DeleteImageResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete an image",
)
async def delete_image(image_id: str, _: _Admin, db: _DB) -> DeleteImageResponse:
    """Delete an image; DB FK cascade removes all analysis records."""
    return await admin_service.delete_image(db, image_id)


# ── System Logs ────────────────────────────────────────────────────────────────

@router.get(
    "/logs",
    response_model=SystemLogListResponse,
    summary="View system logs",
)
async def list_system_logs(
    _: _Admin,
    db: _DB,
    limit: int = Query(default=100, ge=1, le=1000, description="Max log entries to return"),
    level: Optional[str] = Query(default=None, description="Filter by level (INFO/WARNING/ERROR)"),
) -> SystemLogListResponse:
    """Return the most recent system log entries, optionally filtered by level."""
    return await admin_service.list_system_logs(db, limit, level)


# ── Agents ─────────────────────────────────────────────────────────────────────

@router.get(
    "/agents",
    response_model=AgentListResponse,
    summary="List agents with run statistics",
)
async def list_agents(_: _Admin, db: _DB) -> AgentListResponse:
    """Return all pipeline agents with aggregated performance stats."""
    return await admin_service.list_agents(db)

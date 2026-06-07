"""Admin router — 10 protected endpoints.

All handlers require admin privileges via ``require_admin``.
Handlers are thin orchestrators: they call the service layer and
return the result directly — no business logic in this file.
"""
from typing import Annotated, Any, Dict

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import require_admin
from app.models.admin_models import (
    AgentListResponse,
    DeleteImageResponse,
    DeleteProjectResponse,
    FileListResponse,
    ImageListResponse,
    ProjectListResponse,
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
) -> SystemLogListResponse:
    """Return the most recent system log entries."""
    return await admin_service.list_system_logs(db, limit)


# ── Agents ─────────────────────────────────────────────────────────────────────

@router.get(
    "/agents",
    response_model=AgentListResponse,
    summary="List agents with run statistics",
)
async def list_agents(_: _Admin, db: _DB) -> AgentListResponse:
    """Return all pipeline agents with aggregated performance stats."""
    return await admin_service.list_agents(db)

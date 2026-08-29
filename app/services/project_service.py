"""Project deletion as a shared domain operation.

Deleting a project removes its DB rows — FK CASCADE handles the project's Images
and the downstream component/analysis rows — and unlinks the physical upload
files so a deleted project never leaves orphaned assets behind. Both the admin
tools and a user deleting their own account reuse this module, so the cascade
lives in exactly one place. The low-level upload-file primitives also live here
as the lowest layer (admin_service imports them) to keep the dependency one-way.
"""
from pathlib import Path
from typing import List

from fastapi import HTTPException, status
from sqlalchemy import delete as sa_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.orm_models import Image, Project


def unlink_upload_file(file_id: str) -> bool:
    """Delete the physical upload file(s) for *file_id*; best-effort, never raises.

    Returns True if at least one file was removed. Used as a cleanup step after
    deleting an analysis or project — the DB row is the source of truth, so an
    orphaned file left behind is undesirable but non-fatal.
    """
    deleted = False
    for path in Path(settings.UPLOAD_DIR).glob(f"{file_id}.*"):
        try:
            path.unlink()
            deleted = True
        except OSError:
            pass
    return deleted


def upload_file_by_id(file_id: str) -> Path:
    """Locate the on-disk upload file for *file_id* regardless of extension.

    Raises:
        HTTPException 404: If no matching file is found.
    """
    matches = list(Path(settings.UPLOAD_DIR).glob(f"{file_id}.*"))
    if not matches:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No file found for file_id '{file_id}'",
        )
    return matches[0]


async def delete_project(db: AsyncSession, project_id: str) -> bool:
    """Delete a single project and its assets; return True if a row was removed.

    FK CASCADE removes the project's Images and their downstream component and
    analysis rows; the physical image files are unlinked afterwards (best-effort,
    DB-first so the only possible drift is a harmless orphan file). Commits on its
    own so a multi-project loop is resumable after a mid-way error.
    """
    # Gather the file-ids of every image BEFORE the cascade removes the rows.
    paths_result = await db.execute(
        select(Image.ImagePath).where(Image.ProjectId == project_id)
    )
    file_ids = [Path(p).stem for p in paths_result.scalars().all() if p]

    result = await db.execute(sa_delete(Project).where(Project.ProjectId == project_id))
    await db.commit()
    deleted = result.rowcount > 0
    if deleted:
        for file_id in file_ids:
            unlink_upload_file(file_id)
    return deleted


async def delete_user_projects(db: AsyncSession, user_id: str) -> int:
    """Delete every project owned by *user_id*; return the count removed.

    Idempotent and resumable: each project is deleted and committed individually,
    so a re-run (or a later sweep over anonymised accounts that still own rows)
    cleans up whatever remains.
    """
    result = await db.execute(select(Project.ProjectId).where(Project.UserId == user_id))
    project_ids: List[str] = list(result.scalars().all())
    removed = 0
    for project_id in project_ids:
        if await delete_project(db, project_id):
            removed += 1
    return removed

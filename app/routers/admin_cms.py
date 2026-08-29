"""Admin router for the website CMS (draft / publish / history / restore).

All endpoints require the ``cms:manage`` permission (admins only).
"""
from typing import Annotated, Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import require_permission
from app.models.cms_models import (
    DraftResponse,
    PublishResponse,
    RevisionListResponse,
    SaveDraftRequest,
)
from app.security.permissions import PERM_CMS_MANAGE
from app.services import cms_service

router = APIRouter()

_Perm = Annotated[Dict[str, Any], Depends(require_permission(PERM_CMS_MANAGE))]
_DB = Annotated[AsyncSession, Depends(get_db)]


@router.get("/cms/{page_key}/draft", response_model=DraftResponse, summary="Get page draft")
async def get_draft(page_key: str, _: _Perm, db: _DB) -> DraftResponse:
    """Return the working draft (or the published content if no draft yet)."""
    page_key = cms_service.validate_page(page_key)
    return await cms_service.get_draft(db, page_key)


@router.put("/cms/{page_key}/draft", response_model=DraftResponse, summary="Save page draft")
async def save_draft(
    page_key: str, body: SaveDraftRequest, payload: _Perm, db: _DB
) -> DraftResponse:
    """Create or replace the draft for a page (optimistic concurrency)."""
    page_key = cms_service.validate_page(page_key)
    return await cms_service.save_draft(
        db, page_key, body.content, payload.get("sub", ""), body.base_revision_no
    )


@router.post("/cms/{page_key}/publish", response_model=PublishResponse, summary="Publish draft")
async def publish(page_key: str, payload: _Perm, db: _DB) -> PublishResponse:
    """Promote the current draft to a new published revision."""
    page_key = cms_service.validate_page(page_key)
    return await cms_service.publish(db, page_key, payload.get("sub", ""))


@router.get(
    "/cms/{page_key}/revisions",
    response_model=RevisionListResponse,
    summary="List published revisions",
)
async def list_revisions(page_key: str, _: _Perm, db: _DB) -> RevisionListResponse:
    """Return the published revision history for a page."""
    page_key = cms_service.validate_page(page_key)
    revisions = await cms_service.list_revisions(db, page_key)
    return RevisionListResponse(page_key=page_key, revisions=revisions)


@router.post(
    "/cms/{page_key}/restore/{revision_no}",
    response_model=PublishResponse,
    summary="Restore an older revision",
)
async def restore(page_key: str, revision_no: int, payload: _Perm, db: _DB) -> PublishResponse:
    """Re-publish a clone of an older revision as the new current revision."""
    page_key = cms_service.validate_page(page_key)
    return await cms_service.restore(db, page_key, revision_no, payload.get("sub", ""))

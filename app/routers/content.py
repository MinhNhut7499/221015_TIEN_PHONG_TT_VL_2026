"""Public website-content endpoint (no authentication).

Serves the current PUBLISHED CMS content for a page so the frontend can merge it
over its hardcoded defaults. Drafts are never exposed here (admin-only). Cheap
by design: short-TTL in-process cache in the service + ETag/Cache-Control so the
browser and any CDN can cache too.
"""
import hashlib
import json
from typing import Optional

from fastapi import APIRouter, Depends, Header, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.cms_models import ContentResponse
from app.services import cms_service

router = APIRouter()


@router.get(
    "/{page_key}",
    response_model=ContentResponse,
    summary="Public published content for a page",
)
async def get_content(
    page_key: str,
    response: Response,
    if_none_match: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> Response | ContentResponse:
    """Return the published content override for *page_key* (empty if none)."""
    page_key = cms_service.validate_page(page_key)
    content, revision_no = await cms_service.get_published(db, page_key)
    payload = ContentResponse(page_key=page_key, content=content, revision_no=revision_no)
    body = payload.model_dump_json()
    etag = '"' + hashlib.sha256(body.encode("utf-8")).hexdigest()[:32] + '"'
    # Revalidate on every request (cheap via ETag/304) so a publish shows up
    # immediately on the live site — a stale browser cache here is confusing.
    response.headers["Cache-Control"] = "no-cache"
    response.headers["ETag"] = etag
    if if_none_match and if_none_match == etag:
        return Response(status_code=304, headers=dict(response.headers))
    return payload

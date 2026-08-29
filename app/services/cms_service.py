"""Service layer for the simple versioned website CMS.

Model:
- At most one ``draft`` row per page (upserted by ``save_draft``).
- ``published`` rows are an append-only history; exactly one carries
  ``IsCurrent=1`` (enforced by a filtered unique index) — the one served.
- ``publish`` promotes the draft to a new current published revision and drops
  the draft. ``restore`` re-publishes a clone of an older revision.

Published content is served via a short-TTL in-process cache so the public,
unauthenticated ``GET /content/{page}`` endpoint stays cheap; the cache also
makes multi-worker convergence after a publish bounded by the TTL.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.cms_models import (
    DraftResponse,
    PublishResponse,
    RevisionView,
)
from app.models.orm_models import CmsRevision
from app.services.system_log_service import LEVEL_INFO, log_event

logger = logging.getLogger(__name__)

STATUS_DRAFT = "draft"
STATUS_PUBLISHED = "published"

# Pages the CMS knows about (used to validate the path param).
SUPPORTED_PAGES = ("landing", "user")

# Public-content cache: page_key -> (content_dict, revision_no, fetched_at).
_PUBLISHED_CACHE_TTL_SEC = 30.0
_published_cache: Dict[str, Tuple[Dict[str, Any], Optional[int], float]] = {}


def _utc_iso(dt: Optional[datetime]) -> Optional[str]:
    """Serialise a (possibly naive UTC) datetime to an offset-aware ISO string."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _now_utc_naive() -> datetime:
    """Current UTC time as a naive datetime (matches the DATETIME2 convention)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def validate_page(page_key: str) -> str:
    """Lower-case and validate *page_key*, or raise 400."""
    page_key = (page_key or "").lower().strip()
    if page_key not in SUPPORTED_PAGES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown page {page_key!r}. Allowed: {', '.join(SUPPORTED_PAGES)}",
        )
    return page_key


def _parse_content(raw: Optional[str]) -> Dict[str, Any]:
    """Parse a stored ContentJson string into a dict (empty on failure)."""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        logger.warning("Corrupt CMS ContentJson encountered; serving empty override")
        return {}


def invalidate_cache(page_key: Optional[str] = None) -> None:
    """Drop the published-content cache for a page (or all pages)."""
    if page_key is None:
        _published_cache.clear()
    else:
        _published_cache.pop(page_key, None)


async def _current_published(
    db: AsyncSession, page_key: str
) -> Optional[CmsRevision]:
    """Return the current published revision row, or None."""
    result = await db.execute(
        select(CmsRevision).where(
            CmsRevision.PageKey == page_key,
            CmsRevision.Status == STATUS_PUBLISHED,
            CmsRevision.IsCurrent == True,  # noqa: E712
        )
    )
    return result.scalars().first()


async def get_published(db: AsyncSession, page_key: str) -> Tuple[Dict[str, Any], Optional[int]]:
    """Return the (content, revision_no) of the current published revision.

    Cached in-process for a short TTL (the public endpoint is unauthenticated
    and high-traffic). Returns ({}, None) when nothing is published yet so the
    frontend falls back to its hardcoded defaults.
    """
    cached = _published_cache.get(page_key)
    if cached is not None and (time.monotonic() - cached[2]) < _PUBLISHED_CACHE_TTL_SEC:
        return cached[0], cached[1]
    row = await _current_published(db, page_key)
    content = _parse_content(row.ContentJson) if row else {}
    revision_no = row.RevisionNo if row else None
    _published_cache[page_key] = (content, revision_no, time.monotonic())
    return content, revision_no


async def get_draft(db: AsyncSession, page_key: str) -> DraftResponse:
    """Return the working draft, falling back to the published content."""
    result = await db.execute(
        select(CmsRevision).where(
            CmsRevision.PageKey == page_key, CmsRevision.Status == STATUS_DRAFT
        )
    )
    draft = result.scalars().first()
    published = await _current_published(db, page_key)
    base_no = published.RevisionNo if published else 0
    if draft is not None:
        return DraftResponse(
            page_key=page_key,
            content=_parse_content(draft.ContentJson),
            has_draft=True,
            base_revision_no=base_no,
        )
    content = _parse_content(published.ContentJson) if published else {}
    return DraftResponse(
        page_key=page_key, content=content, has_draft=False, base_revision_no=base_no
    )


async def _max_published_no(db: AsyncSession, page_key: str) -> int:
    """Return the highest published RevisionNo for a page (0 if none)."""
    result = await db.execute(
        select(func.max(CmsRevision.RevisionNo)).where(
            CmsRevision.PageKey == page_key, CmsRevision.Status == STATUS_PUBLISHED
        )
    )
    return int(result.scalar() or 0)


async def save_draft(
    db: AsyncSession,
    page_key: str,
    content: Dict[str, Any],
    actor: str,
    base_revision_no: Optional[int] = None,
) -> DraftResponse:
    """Create or replace the single draft for a page (optimistic concurrency)."""
    current_no = await _max_published_no(db, page_key)
    if base_revision_no is not None and base_revision_no != current_no:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "The published content changed since you started editing "
                f"(now revision {current_no}). Reload and reapply your edits."
            ),
        )
    content_json = json.dumps(content, ensure_ascii=False)
    result = await db.execute(
        select(CmsRevision).where(
            CmsRevision.PageKey == page_key, CmsRevision.Status == STATUS_DRAFT
        )
    )
    draft = result.scalars().first()
    if draft is None:
        draft = CmsRevision(
            PageKey=page_key,
            ContentJson=content_json,
            Status=STATUS_DRAFT,
            RevisionNo=0,
            IsCurrent=False,
            CreatedBy=actor or None,
            CreatedAt=_now_utc_naive(),
        )
        db.add(draft)
    else:
        draft.ContentJson = content_json
        draft.UpdatedAt = _now_utc_naive()
    await db.commit()
    return DraftResponse(
        page_key=page_key, content=content, has_draft=True, base_revision_no=current_no
    )


async def _publish_content(
    db: AsyncSession, page_key: str, content_json: str, actor: str
) -> int:
    """Insert *content_json* as the new current published revision.

    Unsets the previous current row first (one transaction) to honour the
    single-current filtered unique index. Returns the new revision number.
    """
    await db.execute(
        sa_update(CmsRevision)
        .where(
            CmsRevision.PageKey == page_key,
            CmsRevision.Status == STATUS_PUBLISHED,
            CmsRevision.IsCurrent == True,  # noqa: E712
        )
        .values(IsCurrent=False)
    )
    new_no = await _max_published_no(db, page_key) + 1
    db.add(
        CmsRevision(
            PageKey=page_key,
            ContentJson=content_json,
            Status=STATUS_PUBLISHED,
            RevisionNo=new_no,
            IsCurrent=True,
            CreatedBy=actor or None,
            CreatedAt=_now_utc_naive(),
        )
    )
    return new_no


async def publish(db: AsyncSession, page_key: str, actor: str) -> PublishResponse:
    """Promote the current draft to a new published revision and drop the draft."""
    result = await db.execute(
        select(CmsRevision).where(
            CmsRevision.PageKey == page_key, CmsRevision.Status == STATUS_DRAFT
        )
    )
    draft = result.scalars().first()
    if draft is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No draft to publish for this page.",
        )
    new_no = await _publish_content(db, page_key, draft.ContentJson, actor)
    await db.delete(draft)
    await db.commit()
    invalidate_cache(page_key)
    await log_event(db, LEVEL_INFO, f"CMS published: page={page_key} rev={new_no} by={actor}")
    return PublishResponse(page_key=page_key, revision_no=new_no)


async def list_revisions(db: AsyncSession, page_key: str) -> List[RevisionView]:
    """Return the published revision history (newest first)."""
    result = await db.execute(
        select(CmsRevision)
        .where(CmsRevision.PageKey == page_key, CmsRevision.Status == STATUS_PUBLISHED)
        .order_by(CmsRevision.RevisionNo.desc())
    )
    return [
        RevisionView(
            revision_no=row.RevisionNo,
            is_current=row.IsCurrent,
            created_at=_utc_iso(row.CreatedAt),
            created_by=row.CreatedBy,
        )
        for row in result.scalars().all()
    ]


async def restore(
    db: AsyncSession, page_key: str, revision_no: int, actor: str
) -> PublishResponse:
    """Re-publish a clone of an older revision as the new current revision."""
    result = await db.execute(
        select(CmsRevision).where(
            CmsRevision.PageKey == page_key,
            CmsRevision.Status == STATUS_PUBLISHED,
            CmsRevision.RevisionNo == revision_no,
        )
    )
    source = result.scalars().first()
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Revision {revision_no} not found for page {page_key!r}.",
        )
    new_no = await _publish_content(db, page_key, source.ContentJson, actor)
    await db.commit()
    invalidate_cache(page_key)
    await log_event(
        db,
        LEVEL_INFO,
        f"CMS restored: page={page_key} from rev={revision_no} as rev={new_no} by={actor}",
    )
    return PublishResponse(page_key=page_key, revision_no=new_no)

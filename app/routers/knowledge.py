"""Knowledge router — read-only access to the architectural-style KB.

Surfaces the curated style knowledge base (``chatbot/knowledge/styles.json``)
to authenticated users so the frontend can show a "knowledge card" when a user
clicks a style name in an analysis result: region, period, defining features,
description, sources, its family, and sibling styles in the same family.

This router performs no computation and touches no database — it simply reads
the in-memory KB via :func:`get_style_kb` and shapes it for display.
"""
import logging
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.dependencies.auth import get_current_active_user
from chatbot.services.style_kb_service import get_style_kb
from chatbot.utils.schemas import StyleEntry

logger = logging.getLogger(__name__)

router = APIRouter()

# Injects auth and rejects deactivated accounts (payload is unused here).
_CurrentUser = Annotated[Dict[str, Any], Depends(get_current_active_user)]


# ── Response models ──────────────────────────────────────────────────────────

class StyleRef(BaseModel):
    """A lightweight reference to a style (for the sibling list / navigation)."""

    id: str
    name: str


class StyleCardResponse(BaseModel):
    """Knowledge-card payload for one architectural style."""

    id: str
    name: str
    aliases: List[str]
    family_id: Optional[str]
    family_name: Optional[str]
    region: List[str]
    period: str
    defining_features: List[str]
    expected_profile: Dict[str, str]
    description: str
    references: List[str]
    aat_id: Optional[str]
    wikidata_id: Optional[str]
    siblings: List[StyleRef]


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get(
    "/style",
    response_model=StyleCardResponse,
    summary="Look up a style knowledge card by free-text name",
    description=(
        "Resolves a free-text style name (exact → alias → fuzzy) to a KB entry "
        "and returns its full knowledge card plus sibling styles in the same "
        "family. Returns 404 when the name matches no KB entry."
    ),
)
async def get_style_by_name(
    _: _CurrentUser,
    name: str = Query(..., min_length=1, description="Free-text style name to resolve."),
) -> StyleCardResponse:
    """Return the knowledge card for the style matching ``name``.

    Args:
        _: Injected JWT payload (auth only).
        name: Free-text style name proposed by the user / analysis result.

    Returns:
        The resolved style's knowledge card with its siblings.

    Raises:
        HTTPException 404: If no KB entry matches the name.
    """
    kb = get_style_kb()
    entry = kb.resolve_card(name)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No knowledge-base entry matches style '{name}'",
        )
    return _build_card(entry)


@router.get(
    "/style/{style_id}",
    response_model=StyleCardResponse,
    summary="Look up a style knowledge card by KB id",
    description=(
        "Returns the knowledge card for an exact KB style id (used when the "
        "frontend navigates between sibling styles). Returns 404 for unknown ids."
    ),
)
async def get_style_by_id(
    style_id: str,
    _: _CurrentUser,
) -> StyleCardResponse:
    """Return the knowledge card for the style with this KB id.

    Raises:
        HTTPException 404: If no KB entry has this id.
    """
    kb = get_style_kb()
    entry = kb.get(style_id)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No knowledge-base entry with id '{style_id}'",
        )
    return _build_card(entry)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _build_card(entry: StyleEntry) -> StyleCardResponse:
    """Shape a KB entry into a display card, including its family siblings."""
    kb = get_style_kb()
    siblings = [
        StyleRef(id=e.id, name=e.name)
        for e in kb.styles_in_family(entry.parent or "")
        if e.id != entry.id
    ]
    siblings.sort(key=lambda s: s.name)
    return StyleCardResponse(
        id=entry.id,
        name=entry.name,
        aliases=entry.aliases,
        family_id=entry.parent,
        family_name=kb.family_name(entry.parent),
        region=entry.region,
        period=entry.period,
        defining_features=entry.defining_features,
        expected_profile=entry.expected_profile,
        description=entry.description,
        references=entry.references,
        aat_id=entry.aat_id,
        wikidata_id=entry.wikidata_id,
        siblings=siblings,
    )

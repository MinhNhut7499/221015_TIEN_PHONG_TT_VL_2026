"""Admin Knowledge-Base router — manage the curated style KB.

All handlers require admin privileges via ``require_admin`` and are thin
orchestrators over ``kb_service`` / ``kb_suggestion_store`` — no business logic
lives here. Service-layer errors are mapped to HTTP status codes at this
boundary: unknown id → 404, invalid input → 400, conflict (duplicate id /
family still in use) → 409.
"""
from typing import Annotated, Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies.auth import require_admin
from app.models.kb_models import (
    DeleteFamilyResponse,
    DeleteStyleResponse,
    DismissSuggestionResponse,
    FamilyCreateRequest,
    FamilyListResponse,
    FamilyRenameRequest,
    FamilyView,
    StyleListResponse,
    StyleUpsert,
    SuggestionListResponse,
)
from app.services import kb_service, kb_suggestion_store
from chatbot.utils.schemas import StyleEntry

router = APIRouter()

# Injects require_admin; handlers only need the 403 side-effect.
_Admin = Annotated[Dict[str, Any], Depends(require_admin)]

# Service errors that signal a conflict rather than a generic bad request.
_CONFLICT_HINTS = ("already exists", "still has")


def _bad_request(exc: ValueError) -> HTTPException:
    """Map a service ValueError to 409 (conflict) or 400 (validation)."""
    message = str(exc)
    if any(hint in message for hint in _CONFLICT_HINTS):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


# ── Styles ───────────────────────────────────────────────────────────────────

@router.get("/styles", response_model=StyleListResponse, summary="List all KB styles")
async def list_styles(_: _Admin) -> StyleListResponse:
    """Return every style entry in the knowledge base."""
    styles = kb_service.list_styles()
    return StyleListResponse(total=len(styles), styles=styles)


@router.get("/styles/{style_id}", response_model=StyleEntry, summary="Get one KB style")
async def get_style(style_id: str, _: _Admin) -> StyleEntry:
    """Return a single style entry by id."""
    try:
        return kb_service.get_style(style_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/styles",
    response_model=StyleEntry,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new KB style",
)
async def create_style(body: StyleUpsert, _: _Admin) -> StyleEntry:
    """Append a new style entry to the KB."""
    try:
        return kb_service.create_style(body)
    except ValueError as exc:
        raise _bad_request(exc) from exc


@router.put("/styles/{style_id}", response_model=StyleEntry, summary="Update a KB style")
async def update_style(style_id: str, body: StyleUpsert, _: _Admin) -> StyleEntry:
    """Overwrite an existing style entry (id is immutable)."""
    try:
        return kb_service.update_style(style_id, body)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise _bad_request(exc) from exc


@router.delete(
    "/styles/{style_id}",
    response_model=DeleteStyleResponse,
    summary="Delete a KB style",
)
async def delete_style(style_id: str, _: _Admin) -> DeleteStyleResponse:
    """Delete a style entry by id."""
    try:
        kb_service.delete_style(style_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return DeleteStyleResponse(id=style_id, deleted=True)


# ── Families ─────────────────────────────────────────────────────────────────

@router.get("/families", response_model=FamilyListResponse, summary="List KB families")
async def list_families(_: _Admin) -> FamilyListResponse:
    """Return all style families (taxonomy groups)."""
    families = [FamilyView(**f) for f in kb_service.list_families()]
    return FamilyListResponse(total=len(families), families=families)


@router.post(
    "/families",
    response_model=FamilyView,
    status_code=status.HTTP_201_CREATED,
    summary="Create a KB family",
)
async def create_family(body: FamilyCreateRequest, _: _Admin) -> FamilyView:
    """Add a new style family."""
    try:
        return FamilyView(**kb_service.create_family(body.id, body.name))
    except ValueError as exc:
        raise _bad_request(exc) from exc


@router.put("/families/{family_id}", response_model=FamilyView, summary="Rename a KB family")
async def rename_family(family_id: str, body: FamilyRenameRequest, _: _Admin) -> FamilyView:
    """Rename an existing style family."""
    try:
        return FamilyView(**kb_service.rename_family(family_id, body.name))
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise _bad_request(exc) from exc


@router.delete(
    "/families/{family_id}",
    response_model=DeleteFamilyResponse,
    summary="Delete a KB family",
)
async def delete_family(family_id: str, _: _Admin) -> DeleteFamilyResponse:
    """Delete a style family (blocked while styles still reference it)."""
    try:
        kb_service.delete_family(family_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise _bad_request(exc) from exc
    return DeleteFamilyResponse(id=family_id, deleted=True)


# ── Suggestion queue ─────────────────────────────────────────────────────────

@router.get(
    "/suggestions",
    response_model=SuggestionListResponse,
    summary="List out-of-KB style suggestions",
)
async def list_suggestions(_: _Admin) -> SuggestionListResponse:
    """Return queued out-of-KB style names awaiting human review."""
    items = kb_suggestion_store.list_suggestions()
    return SuggestionListResponse(total=len(items), suggestions=items)


@router.delete(
    "/suggestions/{name}",
    response_model=DismissSuggestionResponse,
    summary="Dismiss an out-of-KB suggestion",
)
async def dismiss_suggestion(name: str, _: _Admin) -> DismissSuggestionResponse:
    """Remove one suggestion from the review queue."""
    dismissed = kb_suggestion_store.dismiss(name)
    return DismissSuggestionResponse(name=name, dismissed=dismissed)

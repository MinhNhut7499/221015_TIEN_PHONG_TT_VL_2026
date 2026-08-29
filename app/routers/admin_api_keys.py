"""Admin router for managing AI-provider API keys.

All endpoints require the ``apikeys:manage`` permission (admins only). Keys are
stored encrypted; responses never include the plaintext secret.
"""
from typing import Annotated, Any, Dict

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import require_permission
from app.models.api_key_models import (
    ApiKeyCreateRequest,
    ApiKeyListResponse,
    ApiKeyTestRequest,
    ApiKeyTestResponse,
    ApiKeyToggleRequest,
    ApiKeyUpdateRequest,
    ApiKeyView,
    ProviderSummaryResponse,
)
from app.security.permissions import PERM_APIKEYS_MANAGE
from app.services import api_key_service

router = APIRouter()

_Perm = Annotated[Dict[str, Any], Depends(require_permission(PERM_APIKEYS_MANAGE))]
_DB = Annotated[AsyncSession, Depends(get_db)]


@router.get("/api-keys", response_model=ApiKeyListResponse, summary="List provider API keys")
async def list_api_keys(_: _Perm, db: _DB) -> ApiKeyListResponse:
    """Return every stored key (secret masked)."""
    return ApiKeyListResponse(keys=await api_key_service.list_keys(db))


@router.get(
    "/api-keys/providers",
    response_model=ProviderSummaryResponse,
    summary="Resolved credential source per provider",
)
async def list_providers(_: _Perm, db: _DB) -> ProviderSummaryResponse:
    """Show, per provider, whether the active key comes from DB or .env."""
    return ProviderSummaryResponse(providers=await api_key_service.provider_summary(db))


@router.post(
    "/api-keys",
    response_model=ApiKeyView,
    status_code=status.HTTP_201_CREATED,
    summary="Create a provider API key",
)
async def create_api_key(body: ApiKeyCreateRequest, payload: _Perm, db: _DB) -> ApiKeyView:
    """Register a new encrypted provider key."""
    return await api_key_service.create_key(db, body, payload.get("sub", ""))


@router.put("/api-keys/{key_id}", response_model=ApiKeyView, summary="Update a provider API key")
async def update_api_key(
    key_id: str, body: ApiKeyUpdateRequest, payload: _Perm, db: _DB
) -> ApiKeyView:
    """Update metadata and/or rotate the secret of an existing key."""
    return await api_key_service.update_key(db, key_id, body, payload.get("sub", ""))


@router.patch(
    "/api-keys/{key_id}/toggle", response_model=ApiKeyView, summary="Enable/disable a key"
)
async def toggle_api_key(
    key_id: str, body: ApiKeyToggleRequest, payload: _Perm, db: _DB
) -> ApiKeyView:
    """Enable or disable a key."""
    return await api_key_service.toggle_key(db, key_id, body.is_active, payload.get("sub", ""))


@router.delete("/api-keys/{key_id}", summary="Delete a provider API key")
async def delete_api_key(key_id: str, payload: _Perm, db: _DB) -> Dict[str, bool]:
    """Delete a stored key."""
    deleted = await api_key_service.delete_key(db, key_id, payload.get("sub", ""))
    return {"deleted": deleted}


@router.post(
    "/api-keys/test",
    response_model=ApiKeyTestResponse,
    summary="Test a raw key before saving",
)
async def test_api_key(body: ApiKeyTestRequest, _: _Perm) -> ApiKeyTestResponse:
    """Run a connectivity test against the provider for a raw key."""
    return await api_key_service.test_connection(
        body.provider, body.api_key, body.model_override, body.base_url_override
    )


@router.post(
    "/api-keys/{key_id}/test",
    response_model=ApiKeyTestResponse,
    summary="Test a stored key",
)
async def test_stored_api_key(key_id: str, _: _Perm, db: _DB) -> ApiKeyTestResponse:
    """Decrypt and connectivity-test an already-stored key."""
    return await api_key_service.test_stored_key(db, key_id)

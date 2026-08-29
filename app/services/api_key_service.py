"""Admin service for managing AI-provider API keys (DB-backed, encrypted).

Every mutating operation:
1. writes the change + bumps the runtime-config epoch in one transaction,
2. commits durably,
3. reloads the provider runtime (drops the LLM singletons + resets the breaker),
4. writes a best-effort audit log entry — never logging the secret itself.

The plaintext key never leaves this module except into the cipher; reads return
a masked form.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key_models import (
    ApiKeyCreateRequest,
    ApiKeyTestResponse,
    ApiKeyUpdateRequest,
    ApiKeyView,
    ProviderSummary,
)
from app.models.orm_models import ProviderApiKey
from app.security.secret_cipher import (
    CipherUnavailableError,
    cipher_available,
    encrypt_secret,
)
from app.services.system_log_service import LEVEL_INFO, log_event
from chatbot.services import provider_credentials

logger = logging.getLogger(__name__)

_TEST_TIMEOUT_SEC = 12.0


def _iso(dt: Optional[datetime]) -> Optional[str]:
    """Serialise a (possibly naive UTC) datetime to an offset-aware ISO string."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _mask(last4: Optional[str]) -> str:
    """Return a display-safe masked key."""
    return f"••••{last4}" if last4 else "••••"


def _validate_provider(provider: str) -> str:
    """Lower-case and validate *provider*, or raise 400."""
    provider = (provider or "").lower().strip()
    if provider not in provider_credentials.SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported provider {provider!r}. "
                f"Allowed: {', '.join(provider_credentials.SUPPORTED_PROVIDERS)}"
            ),
        )
    return provider


def _to_view(row: ProviderApiKey) -> ApiKeyView:
    """Map an ORM row to its masked API view."""
    env = provider_credentials._env_credentials(row.Provider)  # model/base_url defaults
    return ApiKeyView(
        key_id=row.KeyId,
        provider=row.Provider,
        label=row.Label,
        masked_key=_mask(row.Last4),
        model=row.ModelOverride or env.model,
        base_url=row.BaseUrlOverride or env.base_url,
        priority=row.Priority,
        is_active=row.IsActive,
        last_used_at=_iso(row.LastUsedAt),
        created_at=_iso(row.CreatedAt),
    )


async def list_keys(db: AsyncSession) -> List[ApiKeyView]:
    """Return all stored keys (masked), ordered by provider then priority."""
    result = await db.execute(
        select(ProviderApiKey).order_by(
            ProviderApiKey.Provider, ProviderApiKey.Priority, ProviderApiKey.CreatedAt
        )
    )
    return [_to_view(row) for row in result.scalars().all()]


async def _finalise_write(db: AsyncSession, actor: str, message: str) -> None:
    """Bump epoch, commit, reload runtime, and audit — shared by every write."""
    await provider_credentials.bump_epoch(db)
    await db.commit()
    # Rebuild the LLM singletons so this worker uses the new key immediately;
    # other workers converge via the epoch they just observed.
    from chatbot.services.analysis_orchestrator import reload_provider_runtime

    reload_provider_runtime()
    await log_event(db, LEVEL_INFO, message)


async def create_key(
    db: AsyncSession, payload: ApiKeyCreateRequest, actor: str
) -> ApiKeyView:
    """Create and persist a new encrypted provider key."""
    provider = _validate_provider(payload.provider)
    if not cipher_available():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="APP_ENCRYPTION_KEY is not configured — cannot store an API key securely.",
        )
    try:
        encrypted = encrypt_secret(payload.api_key)
    except CipherUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    row = ProviderApiKey(
        Provider=provider,
        Label=payload.label,
        EncryptedKey=encrypted,
        Last4=payload.api_key[-4:],
        ModelOverride=payload.model_override,
        BaseUrlOverride=payload.base_url_override,
        Priority=payload.priority,
        IsActive=payload.is_active,
        CreatedAt=now,
        UpdatedAt=now,
    )
    db.add(row)
    await db.flush()
    key_id = row.KeyId
    await _finalise_write(
        db, actor, f"API key created: provider={provider} label={payload.label} by={actor}"
    )
    refreshed = await db.get(ProviderApiKey, key_id)
    return _to_view(refreshed)


async def update_key(
    db: AsyncSession, key_id: str, payload: ApiKeyUpdateRequest, actor: str
) -> ApiKeyView:
    """Update an existing key's metadata and/or rotate its secret."""
    row = await db.get(ProviderApiKey, key_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")

    if payload.label is not None:
        row.Label = payload.label
    if payload.model_override is not None:
        row.ModelOverride = payload.model_override or None
    if payload.base_url_override is not None:
        row.BaseUrlOverride = payload.base_url_override or None
    if payload.priority is not None:
        row.Priority = payload.priority
    if payload.is_active is not None:
        row.IsActive = payload.is_active
    if payload.api_key:
        if not cipher_available():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="APP_ENCRYPTION_KEY is not configured — cannot store an API key securely.",
            )
        row.EncryptedKey = encrypt_secret(payload.api_key)
        row.Last4 = payload.api_key[-4:]
    row.UpdatedAt = datetime.now(timezone.utc).replace(tzinfo=None)

    await _finalise_write(db, actor, f"API key updated: id={key_id} by={actor}")
    refreshed = await db.get(ProviderApiKey, key_id)
    return _to_view(refreshed)


async def toggle_key(
    db: AsyncSession, key_id: str, is_active: bool, actor: str
) -> ApiKeyView:
    """Enable or disable a key without changing anything else."""
    row = await db.get(ProviderApiKey, key_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    row.IsActive = is_active
    row.UpdatedAt = datetime.now(timezone.utc).replace(tzinfo=None)
    await _finalise_write(
        db, actor, f"API key {'enabled' if is_active else 'disabled'}: id={key_id} by={actor}"
    )
    refreshed = await db.get(ProviderApiKey, key_id)
    return _to_view(refreshed)


async def delete_key(db: AsyncSession, key_id: str, actor: str) -> bool:
    """Delete a key. Returns True if a row was removed."""
    result = await db.execute(
        sa_delete(ProviderApiKey).where(ProviderApiKey.KeyId == key_id)
    )
    deleted = (result.rowcount or 0) > 0
    if not deleted:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    await _finalise_write(db, actor, f"API key deleted: id={key_id} by={actor}")
    return True


async def provider_summary(db: AsyncSession) -> List[ProviderSummary]:
    """Summarise, per supported provider, which credential is in effect."""
    # active key counts per provider
    result = await db.execute(
        select(ProviderApiKey.Provider).where(ProviderApiKey.IsActive == True)  # noqa: E712
    )
    counts: dict = {}
    for (provider,) in result.all():
        counts[(provider or "").lower()] = counts.get((provider or "").lower(), 0) + 1

    summaries: List[ProviderSummary] = []
    for provider in provider_credentials.SUPPORTED_PROVIDERS:
        cred = provider_credentials.get_credentials(provider)
        summaries.append(
            ProviderSummary(
                provider=provider,
                source=cred.source if cred.key else "none",
                configured=bool(cred.key),
                model=cred.model,
                active_key_count=counts.get(provider, 0),
                masked_key=_mask(cred.key[-4:]) if cred.key else None,
            )
        )
    return summaries


def _build_transient_service(provider: str, api_key: str, model: str, base_url: Optional[str]):
    """Build a throwaway service instance for a connectivity test."""
    if provider == "gemini":
        from chatbot.services.gemini_service import GeminiService

        return GeminiService(api_key=api_key, model=model)
    if provider == "openai":
        from chatbot.services.openai_service import OpenAIService

        return OpenAIService(api_key=api_key, model=model)
    if provider == "deepseek":
        from chatbot.services.deepseek_service import DeepSeekService

        return DeepSeekService(api_key=api_key, base_url=base_url or "", model=model)
    from chatbot.services.grok_service import GrokService

    return GrokService(api_key=api_key, model=model, base_url=base_url or "")


async def test_connection(
    provider: str,
    api_key: str,
    model_override: Optional[str] = None,
    base_url_override: Optional[str] = None,
) -> ApiKeyTestResponse:
    """Verify a raw key reaches the provider (timeout-bounded). Never raises."""
    provider = _validate_provider(provider)
    env = provider_credentials._env_credentials(provider)
    model = model_override or env.model
    base_url = base_url_override or env.base_url
    try:
        svc = _build_transient_service(provider, api_key, model, base_url)
        ok = await asyncio.wait_for(svc.is_available(), timeout=_TEST_TIMEOUT_SEC)
        return ApiKeyTestResponse(
            ok=bool(ok),
            detail="Connection succeeded" if ok else "Provider reported unavailable",
        )
    except asyncio.TimeoutError:
        return ApiKeyTestResponse(ok=False, detail="Connection timed out")
    except Exception as exc:  # noqa: BLE001 — boundary: report any failure to the admin
        logger.warning("API key test failed for provider=%s: %s", provider, exc)
        return ApiKeyTestResponse(ok=False, detail=f"Connection failed: {exc}")


async def test_stored_key(db: AsyncSession, key_id: str) -> ApiKeyTestResponse:
    """Decrypt a stored key and run a connectivity test."""
    from app.security.secret_cipher import decrypt_secret

    row = await db.get(ProviderApiKey, key_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    plaintext = decrypt_secret(row.EncryptedKey)
    if not plaintext:
        return ApiKeyTestResponse(
            ok=False, detail="Stored key could not be decrypted (encryption key changed?)"
        )
    return await test_connection(
        row.Provider, plaintext, row.ModelOverride, row.BaseUrlOverride
    )

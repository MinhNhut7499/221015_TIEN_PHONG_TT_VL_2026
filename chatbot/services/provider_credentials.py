"""Single source of truth for AI-provider credentials (DB-backed, env fallback).

Provider keys may be managed by an admin in the database (encrypted) instead of
being baked into ``.env``. This module resolves, per provider, the active
``{key, model, base_url}`` to use — preferring the highest-priority active DB
key and falling back to the matching ``settings.*`` value whenever a DB key is
absent, undecryptable, or the feature is switched off.

Multi-worker convergence (prod runs several uvicorn workers, each its own
process):
- A monotonic ``ProviderConfigEpoch`` counter is bumped on every key write.
- Each worker keeps an in-memory snapshot tagged with the epoch it was built
  from, and caches the epoch read for ``RUNTIME_EPOCH_TTL_SEC``.
- ``ensure_fresh(db)`` re-reads the epoch (cheaply, throttled by the TTL) and
  rebuilds the snapshot when it changed — so a key edit on one worker reaches
  the others within the TTL window, no broker required.

Everything here is fail-safe: a missing table, a DB outage, or a decrypt failure
degrades to the ``.env`` keys and logs, never raising into the request path.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Dict, Optional

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.security.secret_cipher import decrypt_secret

logger = logging.getLogger(__name__)

# Providers the resolver knows how to map to env defaults. Used to validate the
# Provider column on write (chống typo tạo provider chết).
SUPPORTED_PROVIDERS = ("gemini", "openai", "deepseek", "xai")

# Providers that must be configured for the analysis pipeline to run at all.
_CORE_PROVIDERS = ("gemini", "openai", "deepseek")


@dataclass(frozen=True)
class ProviderCredentials:
    """Resolved credentials for a single provider."""

    provider: str
    key: str
    model: str
    base_url: Optional[str]
    source: str  # "db" | "env"


# ── In-memory snapshot (per worker process) ─────────────────────────────────
_snapshot: Dict[str, ProviderCredentials] = {}
_snapshot_epoch: Optional[int] = None
_epoch_cache: Optional[int] = None
_epoch_cached_at: float = 0.0


def _env_credentials(provider: str) -> ProviderCredentials:
    """Build credentials for *provider* straight from settings (.env)."""
    mapping = {
        "gemini": (settings.GEMINI_API_KEY, settings.GEMINI_MODEL, None),
        "openai": (settings.OPENAI_API_KEY, settings.OPENAI_MODEL, None),
        "deepseek": (
            settings.DEEPSEEK_API_KEY,
            settings.DEEPSEEK_MODEL,
            settings.DEEPSEEK_BASE_URL,
        ),
        "xai": (settings.XAI_API_KEY, settings.GROK_MODEL, settings.XAI_BASE_URL),
    }
    key, model, base_url = mapping[provider]
    return ProviderCredentials(
        provider=provider, key=key, model=model, base_url=base_url, source="env"
    )


def get_credentials(provider: str) -> ProviderCredentials:
    """Return the credentials to use for *provider* (DB snapshot or env).

    Pure/synchronous so the LLM service singletons can be built without an async
    DB call. Reflects the snapshot as last refreshed by ``ensure_fresh`` /
    ``refresh_snapshot``; falls back to ``.env`` when no DB key applies.

    Raises:
        ValueError: if *provider* is not a supported provider key.
    """
    provider = provider.lower()
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Unsupported provider: {provider!r}")
    if not settings.PROVIDER_KEYS_FROM_DB:
        return _env_credentials(provider)
    snap = _snapshot.get(provider)
    if snap is not None and snap.key:
        return snap
    return _env_credentials(provider)


def is_pipeline_configured() -> bool:
    """Return True if every core provider has a usable key (DB or env)."""
    return all(bool(get_credentials(p).key) for p in _CORE_PROVIDERS)


async def _read_epoch(db: AsyncSession) -> Optional[int]:
    """Read the current config epoch, or None when unavailable (fail-safe)."""
    try:
        result = await db.execute(
            sa_text("SELECT Epoch FROM ProviderConfigEpoch WHERE Id = 1")
        )
        row = result.first()
        return int(row[0]) if row is not None else None
    except Exception as exc:  # noqa: BLE001 — boundary: DB may be down / table absent
        logger.warning("Could not read ProviderConfigEpoch (using current snapshot): %s", exc)
        return None


async def _read_epoch_cached(db: AsyncSession) -> Optional[int]:
    """Read the epoch, throttled to one DB hit per RUNTIME_EPOCH_TTL_SEC."""
    global _epoch_cache, _epoch_cached_at
    now = time.monotonic()
    if _epoch_cache is not None and (now - _epoch_cached_at) < settings.RUNTIME_EPOCH_TTL_SEC:
        return _epoch_cache
    epoch = await _read_epoch(db)
    _epoch_cache = epoch
    _epoch_cached_at = now
    return epoch


async def refresh_snapshot(db: AsyncSession, epoch: Optional[int] = None) -> None:
    """Rebuild the in-memory snapshot from the DB (highest-priority active key).

    Best-effort: any failure leaves the previous snapshot intact and logs.
    """
    global _snapshot, _snapshot_epoch
    if not settings.PROVIDER_KEYS_FROM_DB:
        _snapshot = {}
        _snapshot_epoch = epoch if epoch is not None else await _read_epoch(db)
        return
    try:
        result = await db.execute(
            sa_text(
                "SELECT Provider, EncryptedKey, ModelOverride, BaseUrlOverride "
                "FROM ProviderApiKeys WHERE IsActive = 1 "
                "ORDER BY Provider, Priority ASC, CreatedAt ASC"
            )
        )
        rows = result.all()
    except Exception as exc:  # noqa: BLE001 — boundary: table may not exist yet
        logger.warning("Could not load ProviderApiKeys (falling back to env): %s", exc)
        return

    new_snapshot: Dict[str, ProviderCredentials] = {}
    for provider, encrypted, model_override, base_url_override in rows:
        provider = (provider or "").lower()
        if provider not in SUPPORTED_PROVIDERS or provider in new_snapshot:
            continue  # keep the first (lowest Priority) usable row per provider
        plaintext = decrypt_secret(encrypted)
        if not plaintext:
            continue  # decrypt failed → skip, env fallback covers it
        env = _env_credentials(provider)
        new_snapshot[provider] = ProviderCredentials(
            provider=provider,
            key=plaintext,
            model=model_override or env.model,
            base_url=base_url_override or env.base_url,
            source="db",
        )
    _snapshot = new_snapshot
    _snapshot_epoch = epoch if epoch is not None else await _read_epoch(db)


async def ensure_fresh(db: AsyncSession) -> bool:
    """Refresh the snapshot if the DB epoch changed. Returns True if rebuilt.

    Cheap on the hot path: only re-reads the epoch once per TTL, and only
    rebuilds the snapshot when the epoch actually moved or was never loaded.
    """
    epoch = await _read_epoch_cached(db)
    if _snapshot_epoch is not None and epoch == _snapshot_epoch:
        return False
    await refresh_snapshot(db, epoch)
    return True


async def bump_epoch(db: AsyncSession) -> None:
    """Increment the config epoch so other workers rebuild their snapshot.

    Caller is responsible for committing the surrounding transaction.
    """
    await db.execute(
        sa_text(
            "UPDATE ProviderConfigEpoch SET Epoch = Epoch + 1, "
            "UpdatedAt = SYSUTCDATETIME() WHERE Id = 1"
        )
    )


def invalidate_local() -> None:
    """Force the next ``ensure_fresh`` to rebuild the snapshot on this worker."""
    global _snapshot_epoch, _epoch_cache
    _snapshot_epoch = None
    _epoch_cache = None

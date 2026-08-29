"""Symmetric encryption for provider API keys stored in the database.

Provider keys live encrypted at rest. This module is the single boundary that
turns a plaintext key into a ciphertext string (and back), using Fernet with the
key material from ``settings.APP_ENCRYPTION_KEY``.

Design choices:
- ``MultiFernet`` is used so ``APP_ENCRYPTION_KEY`` may hold a comma-separated
  list of keys. The FIRST key always encrypts; EVERY key is tried on decrypt.
  This lets the encryption key be rotated (prepend a new key, re-encrypt over
  time, drop the old one) without a schema change or downtime.
- Decryption NEVER raises on bad/missing input — it returns ``None`` so callers
  (the credential resolver) can fail safe by falling back to the .env keys.
- When ``APP_ENCRYPTION_KEY`` is empty the cipher is considered DISABLED: encrypt
  raises (storing a key makes no sense without a cipher) and decrypt returns None.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.config import settings

logger = logging.getLogger(__name__)


class CipherUnavailableError(RuntimeError):
    """Raised when an encrypt is attempted but APP_ENCRYPTION_KEY is not set."""


@lru_cache()
def _get_cipher() -> Optional[MultiFernet]:
    """Build the MultiFernet from settings, or None when no key is configured.

    Cached for the process lifetime — APP_ENCRYPTION_KEY does not change at
    runtime (it is an .env value, not a DB-managed one).
    """
    raw = (settings.APP_ENCRYPTION_KEY or "").strip()
    if not raw:
        return None
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    try:
        return MultiFernet([Fernet(k.encode("utf-8")) for k in keys])
    except (ValueError, TypeError) as exc:
        # A malformed APP_ENCRYPTION_KEY is an operator error: log loudly and
        # treat the cipher as unavailable rather than crashing the process.
        logger.error("APP_ENCRYPTION_KEY is malformed; cipher disabled: %s", exc)
        return None


def cipher_available() -> bool:
    """Return True if an encryption key is configured and usable."""
    return _get_cipher() is not None


def encrypt_secret(plaintext: str) -> str:
    """Encrypt *plaintext* and return the ciphertext as a UTF-8 string.

    Raises:
        CipherUnavailableError: if APP_ENCRYPTION_KEY is not configured.
    """
    cipher = _get_cipher()
    if cipher is None:
        raise CipherUnavailableError(
            "APP_ENCRYPTION_KEY is not set — cannot store an encrypted API key. "
            "Generate one with Fernet.generate_key() and add it to .env."
        )
    return cipher.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: Optional[str]) -> Optional[str]:
    """Decrypt *ciphertext* back to plaintext, or return None on any failure.

    Never raises: a missing cipher, a malformed token, or a key that no longer
    decrypts all return None so the caller can fall back to the .env keys.
    """
    if not ciphertext:
        return None
    cipher = _get_cipher()
    if cipher is None:
        return None
    try:
        return cipher.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError) as exc:
        logger.error("Failed to decrypt a stored API key (fail-safe to env): %s", exc)
        return None

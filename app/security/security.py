"""JWT token operations and password hashing.

Provides the security primitives used across the application:
- bcrypt password hashing / verification
- JWT access & refresh token creation
- JWT decoding with structured error handling
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import bcrypt
from jose import JWTError, jwt

from app.config import settings


class TokenError(Exception):
    """Raised when a JWT token cannot be decoded or fails validation."""


# ── Password hashing ───────────────────────────────────────────────────────────

def hash_password(plain_password: str) -> str:
    """Return a bcrypt-hashed version of *plain_password*.

    Uses a fresh random salt on every call so identical passwords
    produce different hashes.
    """
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Return True if *plain_password* matches *hashed_password*.

    Safe against timing attacks via constant-time comparison inside bcrypt.
    """
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


# ── Token creation ─────────────────────────────────────────────────────────────

def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a signed JWT access token containing *data* as payload.

    Default expiry is controlled by JWT_ACCESS_TOKEN_EXPIRE_MINUTES in config.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta
        or timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "token_type": "access"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(data: Dict[str, Any]) -> str:
    """Create a signed JWT refresh token with a longer expiry.

    Refresh tokens are used to obtain new access tokens without re-authentication.
    Expiry is controlled by JWT_REFRESH_TOKEN_EXPIRE_DAYS in config.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
    )
    to_encode.update({"exp": expire, "token_type": "refresh"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


# ── Token decoding ─────────────────────────────────────────────────────────────

def decode_token(token: str) -> Dict[str, Any]:
    """Decode and validate a JWT token, returning its payload dict.

    Raises:
        TokenError: if the token is malformed, expired, or has an invalid signature.
    """
    try:
        payload: Dict[str, Any] = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except JWTError as exc:
        raise TokenError(f"Token validation failed: {exc}") from exc


def get_token_subject(token: str) -> str:
    """Extract and return the 'sub' (subject / user ID) claim from a JWT token.

    Raises:
        TokenError: if the token is invalid or the 'sub' claim is absent.
    """
    payload = decode_token(token)
    subject: Optional[str] = payload.get("sub")
    if not subject:
        raise TokenError("Token is missing the required 'sub' claim")
    return subject

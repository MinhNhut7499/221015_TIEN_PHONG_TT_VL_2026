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


# ── Password reset token ─────────────────────────────────────────────────────

_PASSWORD_RESET_PURPOSE = "pwd_reset"


def create_password_reset_token(user_id: str) -> str:
    """Create a short-lived, single-purpose JWT for resetting a password.

    The token is stateless (no DB row needed): it carries the user id and a
    ``purpose`` claim verified by :func:`verify_password_reset_token`. Expiry is
    controlled by ``PASSWORD_RESET_EXPIRE_MINUTES`` in config.
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES
    )
    to_encode: Dict[str, Any] = {
        "sub": user_id,
        "purpose": _PASSWORD_RESET_PURPOSE,
        "exp": expire,
    }
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def verify_password_reset_token(token: str) -> str:
    """Decode a password-reset token and return its subject (user id).

    Raises:
        TokenError: if the token is invalid, expired, or not a reset token.
    """
    payload = decode_token(token)
    if payload.get("purpose") != _PASSWORD_RESET_PURPOSE:
        raise TokenError("Token is not a password-reset token")
    subject: Optional[str] = payload.get("sub")
    if not subject:
        raise TokenError("Reset token is missing the required 'sub' claim")
    return subject


# ── Email verification token ──────────────────────────────────────────────────

_EMAIL_VERIFY_PURPOSE = "email_verify"


def create_email_verification_token(email: str, name: str, password_hash: str) -> str:
    """Create a single-purpose JWT carrying a PENDING registration.

    No account is written until the user clicks the emailed link, so the token
    carries the data needed to create the account on verification: the email,
    the display name, and the already-bcrypt-hashed password (never plaintext).
    Expiry is controlled by ``EMAIL_VERIFY_EXPIRE_MINUTES`` in config.
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.EMAIL_VERIFY_EXPIRE_MINUTES
    )
    to_encode: Dict[str, Any] = {
        "email": email,
        "name": name,
        "pwd": password_hash,
        "purpose": _EMAIL_VERIFY_PURPOSE,
        "exp": expire,
    }
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def verify_email_verification_token(token: str) -> Dict[str, str]:
    """Decode an email-verification token into its pending-registration data.

    Returns:
        A dict with ``email``, ``name`` and ``password_hash``.

    Raises:
        TokenError: if the token is invalid, expired, or not a verification token.
    """
    payload = decode_token(token)
    if payload.get("purpose") != _EMAIL_VERIFY_PURPOSE:
        raise TokenError("Token is not an email-verification token")
    email: Optional[str] = payload.get("email")
    password_hash: Optional[str] = payload.get("pwd")
    if not email or not password_hash:
        raise TokenError("Verification token is missing required claims")
    return {
        "email": email,
        "name": payload.get("name") or email,
        "password_hash": password_hash,
    }


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

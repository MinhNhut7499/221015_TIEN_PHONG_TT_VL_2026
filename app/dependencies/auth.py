"""Reusable FastAPI authentication and authorisation dependencies.

These functions are designed to be injected via ``Depends()``.
JWT primitives (encode/decode) stay in ``app/security/security.py``;
FastAPI-specific wiring lives here to avoid circular imports.
"""
from typing import Any, Dict

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.security.security import TokenError, decode_token, get_token_subject

_bearer_scheme = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> str:
    """Validate Bearer token and return the user subject (``sub`` claim).

    Raises:
        HTTPException 401: If the token is absent, malformed, or expired.
    """
    try:
        return get_token_subject(credentials.credentials)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_current_user_payload(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> Dict[str, Any]:
    """Validate Bearer token and return the full decoded JWT payload dict.

    Raises:
        HTTPException 401: If the token is absent, malformed, or expired.
    """
    try:
        return decode_token(credentials.credentials)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def require_admin(
    payload: Dict[str, Any] = Depends(get_current_user_payload),
) -> Dict[str, Any]:
    """Require the caller to hold admin privileges.

    Checks ``payload["role"] == "admin"`` first.
    Falls back to the ``ADMIN_EMAILS`` whitelist for tokens issued before the
    ``role`` claim was added (backward-compatible transition period).

    Raises:
        HTTPException 403: If the caller is not an admin.
    """
    role: str = payload.get("role", "")
    email: str = payload.get("email", "").lower()
    if role == "admin" or email in settings.admin_emails_list:
        return payload
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin access required",
    )

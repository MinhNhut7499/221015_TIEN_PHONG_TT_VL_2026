"""Reusable FastAPI authentication and authorisation dependencies.

These functions are designed to be injected via ``Depends()``.
JWT primitives (encode/decode) stay in ``app/security/security.py``;
FastAPI-specific wiring lives here to avoid circular imports.
"""
from typing import Any, Callable, Dict

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.orm_models import User
from app.security.permissions import PERM_ADMIN, role_has_permission
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


async def assert_account_active(db: AsyncSession, user_id: str) -> None:
    """Reject the request if the account exists in the DB and is deactivated.

    This is the single choke-point for "is this principal still allowed?". Any
    endpoint that mints or exchanges tokens (e.g. a future ``/auth/refresh``)
    MUST call this — otherwise a deleted/deactivated account could keep issuing
    fresh access tokens via a refresh token. A user not present in the database
    is allowed through (synthetic test tokens / legacy tokens), mirroring the
    lenient philosophy of ``_persist_result``.

    Raises:
        HTTPException 403: If the user exists and ``IsActive`` is False.
    """
    result = await db.execute(select(User.IsActive).where(User.UserId == user_id))
    is_active = result.scalar_one_or_none()
    if is_active is False:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản đã bị vô hiệu hóa",
        )


async def get_current_active_user(
    payload: Dict[str, Any] = Depends(get_current_user_payload),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Validate the token and reject explicitly deactivated accounts.

    Looks up ``User.IsActive`` by the token subject via ``assert_account_active``.

    Raises:
        HTTPException 403: If the user exists and ``IsActive`` is False.
    """
    await assert_account_active(db, payload.get("sub", ""))
    return payload


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


def _payload_role(payload: Dict[str, Any]) -> str:
    """Resolve the caller's effective role, honouring the ADMIN_EMAILS bootstrap."""
    role = (payload.get("role") or "").lower()
    if role:
        return role
    email = (payload.get("email") or "").lower()
    return "admin" if email in settings.admin_emails_list else "user"


def require_permission(permission: str) -> Callable[..., Dict[str, Any]]:
    """Build a dependency that requires the caller's role to grant *permission*.

    The lightweight RBAC layer (``app/security/permissions.py``): the role name
    from the JWT (or the ADMIN_EMAILS bootstrap) is mapped to a permission set.
    Returns the JWT payload so handlers can read ``sub``/``email`` for auditing.

    Raises:
        HTTPException 403: If the caller's role does not grant the permission.
    """

    def _dependency(
        payload: Dict[str, Any] = Depends(get_current_user_payload),
    ) -> Dict[str, Any]:
        role = _payload_role(payload)
        if role_has_permission(role, permission) or role_has_permission(role, PERM_ADMIN):
            return payload
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this action",
        )

    return _dependency

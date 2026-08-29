"""Hybrid mobile app login sessions (Cloud-Sync Polling).

Backs the Google login flow for the Flutter WebView app: the web (running
inside the app) registers a pending session, the app opens Google OAuth in a
Chrome Custom Tab, the flutter callback stores the issued JWT pair against the
session, and the web polls until it can claim the tokens.

Security properties (all enforced by conditional SQL, not Python-side checks,
so they hold under concurrent requests):
- One-time use: ``poll_session`` claims the tokens with a single
  ``DELETE ... OUTPUT`` so only the first poll ever receives them.
- TTL: every state transition requires ``ExpiresAt > now``.
- ``complete_session`` only writes into a still-pending, unexpired row.
- Tokens are never written to logs.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.orm_models import LoginSession

logger = logging.getLogger(__name__)

# Session lifecycle states stored in LoginSessions.Status.
STATUS_PENDING = "pending"
STATUS_COMPLETED = "completed"
# Returned to the poller when the session is gone or past its TTL.
STATUS_EXPIRED = "expired"


def _utcnow() -> datetime:
    """Return the current UTC time as a naive datetime.

    SQL Server DATETIME2 columns are read back as naive values, so comparisons
    must also be naive to avoid offset-naive/offset-aware TypeErrors.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def create_session(db: AsyncSession, session_id: str) -> None:
    """Register (or reset) a pending login session for *session_id*.

    Opportunistically deletes every expired session first (covers completed
    sessions that were never polled), then upserts the row as ``pending`` with
    a fresh TTL and no tokens.
    """
    now = _utcnow()
    await db.execute(delete(LoginSession).where(LoginSession.ExpiresAt < now))

    expires_at = now + timedelta(minutes=settings.LOGIN_SESSION_TTL_MIN)
    result = await db.execute(
        update(LoginSession)
        .where(LoginSession.SessionId == session_id)
        .values(
            Status=STATUS_PENDING,
            AccessToken=None,
            RefreshToken=None,
            UserId=None,
            CompletedAt=None,
            ExpiresAt=expires_at,
        )
    )
    if result.rowcount == 0:
        await db.execute(
            insert(LoginSession).values(
                SessionId=session_id,
                Status=STATUS_PENDING,
                ExpiresAt=expires_at,
                CreatedAt=now,
            )
        )


async def session_is_pending(db: AsyncSession, session_id: str) -> bool:
    """Return True if *session_id* is a still-pending, unexpired session.

    Used by the flutter callback to reject forged/unknown ``state`` values
    before exchanging the Google code (so it cannot create stray accounts).
    """
    now = _utcnow()
    result = await db.execute(
        select(LoginSession.SessionId).where(
            LoginSession.SessionId == session_id,
            LoginSession.Status == STATUS_PENDING,
            LoginSession.ExpiresAt > now,
        )
    )
    return result.first() is not None


async def complete_session(
    db: AsyncSession,
    session_id: str,
    access_token: str,
    refresh_token: str,
    user_id: str,
) -> bool:
    """Attach the issued JWT pair to a pending session.

    Conditional update (compare-and-set): only a row that is still ``pending``
    and unexpired is written. Returns True on success; False if the session is
    missing, expired, or already completed — in which case nothing is created
    or overwritten.
    """
    now = _utcnow()
    result = await db.execute(
        update(LoginSession)
        .where(
            LoginSession.SessionId == session_id,
            LoginSession.Status == STATUS_PENDING,
            LoginSession.ExpiresAt > now,
        )
        .values(
            Status=STATUS_COMPLETED,
            AccessToken=access_token,
            RefreshToken=refresh_token,
            UserId=user_id,
            CompletedAt=now,
        )
    )
    return result.rowcount == 1


async def poll_session(db: AsyncSession, session_id: str) -> Dict[str, Any]:
    """Return the session status, claiming the tokens exactly once.

    A single ``DELETE ... OUTPUT`` atomically removes a completed, unexpired
    row and returns its tokens, so two concurrent polls can never both receive
    them. Pending/expired states are reported without handing out tokens.
    """
    now = _utcnow()
    claimed = await db.execute(
        delete(LoginSession)
        .where(
            LoginSession.SessionId == session_id,
            LoginSession.Status == STATUS_COMPLETED,
            LoginSession.ExpiresAt > now,
        )
        .returning(LoginSession.AccessToken, LoginSession.RefreshToken)
    )
    row = claimed.first()
    if row is not None:
        return {
            "status": STATUS_COMPLETED,
            "access_token": row[0],
            "refresh_token": row[1],
        }

    result = await db.execute(
        select(LoginSession.Status, LoginSession.ExpiresAt).where(
            LoginSession.SessionId == session_id
        )
    )
    existing = result.first()
    if existing is None:
        return {"status": STATUS_EXPIRED}

    _status, expires_at = existing
    if expires_at is None or expires_at <= now:
        await db.execute(
            delete(LoginSession).where(LoginSession.SessionId == session_id)
        )
        return {"status": STATUS_EXPIRED}

    return {"status": STATUS_PENDING}

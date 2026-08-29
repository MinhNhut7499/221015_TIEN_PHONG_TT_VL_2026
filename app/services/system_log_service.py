"""System audit logging.

Writes application-level events (logins, account changes, deletions,
analysis outcomes) to the ``SystemLogs`` table so the admin UI can show a
real audit trail. Logging is best-effort: a failure here must never break
the calling request, so every write is wrapped in try/except.
"""
import logging
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm_models import SystemLog

logger = logging.getLogger(__name__)

# Canonical log levels stored in SystemLogs.LogLevel.
LEVEL_INFO = "INFO"
LEVEL_WARNING = "WARNING"
LEVEL_ERROR = "ERROR"


async def log_event(db: AsyncSession, level: str, message: str) -> None:
    """Persist a single audit log entry; swallow any failure.

    Args:
        db: Active async session (reused from the request).
        level: One of ``INFO`` / ``WARNING`` / ``ERROR``.
        message: Human-readable description of the event.
    """
    try:
        db.add(
            SystemLog(
                LogId=str(uuid4()),
                LogLevel=level.upper(),
                Message=message,
            )
        )
        await db.commit()
    except Exception as exc:  # best-effort: never break the caller
        logger.warning("Failed to write SystemLog entry: %s", exc)
        try:
            await db.rollback()
        except Exception:  # pragma: no cover - rollback on a dead session
            pass

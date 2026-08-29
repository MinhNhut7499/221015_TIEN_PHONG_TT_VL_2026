"""User-initiated account + data deletion (Google Play / App Store compliance).

Strategy — ANONYMISE the ``User`` row and RETAIN the (now PII-free) financial
ledger. The billing tables (PaymentTransaction / TokenLedger / Refund) reference
``Users.UserId`` with no ON DELETE CASCADE, on purpose, so accounting rows and the
``TokenBalance == Σ Delta`` invariant survive. Hard-deleting the user row would
violate those FKs; scrubbing it erases all PII while keeping references valid.

The flow is "lock first, clean up after": a single compare-and-set UPDATE is the
atomic, idempotent moment the account becomes deleted (login + upload stop
immediately); content/file removal then runs as a resumable step. DB+filesystem
cannot be made transactionally atomic, so we do not pretend to — we make the
heavy part safe to re-run instead.
"""
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm_models import User
from app.services import project_service
from app.services.system_log_service import LEVEL_INFO, log_event


@dataclass
class AccountDeletionResult:
    """Outcome of a self-deletion request."""

    deleted: bool
    projects_deleted: int = 0


def _anonymised_email(user_id: str) -> str:
    """Build a unique, non-routable placeholder email (RFC 2606 ``.invalid``)."""
    return f"deleted+{user_id}@deleted.invalid"


async def delete_own_account(db: AsyncSession, user_id: str) -> AccountDeletionResult:
    """Delete the caller's own account and data; anonymise + retain the ledger.

    Sequence:
        1. CAS UPDATE locks + scrubs the ``User`` row (guarded by ``IsActive=1``).
           A zero rowcount means it was already deleted / a concurrent request
           won, so we return idempotently without touching anything else.
        2. Delete the user's projects, images and physical files (resumable).
        3. Audit-log the deletion by opaque id (never the now-erased email).

    Returns:
        ``AccountDeletionResult`` with ``deleted`` False when already deleted.
    """
    # 1. Atomic lock + PII scrub. The guard makes concurrent/repeat calls a no-op.
    result = await db.execute(
        sa_update(User)
        .where(User.UserId == user_id, User.IsActive == True)  # noqa: E712
        .values(
            IsActive=False,
            Email=_anonymised_email(user_id),
            Name="Deleted User",
            Picture=None,
            GoogleSub=None,
            PasswordHash=None,
            UpdatedAt=datetime.now(timezone.utc),
        )
    )
    await db.commit()
    if result.rowcount == 0:
        return AccountDeletionResult(deleted=False)

    # 2. Remove owned content + on-disk files (idempotent, commits per project).
    projects_deleted = await project_service.delete_user_projects(db, user_id)

    # 3. Audit by id only — the email has just been erased; do not re-introduce PII.
    await log_event(db, LEVEL_INFO, f"User self-deleted account: {user_id}")

    return AccountDeletionResult(deleted=True, projects_deleted=projects_deleted)

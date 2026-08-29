"""Token wallet service — the ONLY place that mutates token balances.

The append-only ``TokenLedger`` is the source of truth; ``Users.TokenBalance``
is a cache kept in lock-step by ``apply_ledger``. The system invariant is::

    Users.TokenBalance == SUM(TokenLedger.Delta)  (per user)

``apply_ledger`` is the single primitive every credit/debit goes through. It is
atomic and idempotent:

* The balance change is a lock-free conditional UPDATE with an ``OUTPUT`` clause
  so the new balance is read in the same statement (no read-modify-write race).
* The matching ledger row carries a UNIQUE ``IdempotencyKey``; a duplicate key
  (replay, double callback, concurrent retry) rolls back via a SAVEPOINT and
  becomes a no-op. This makes every economic event exactly-once under any race.

``apply_ledger`` runs inside the caller's transaction and does NOT commit — the
caller controls the transaction boundary (e.g. the IPN handler commits the CAS
status flip and the credit together).
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Tuple
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.billing_models import LedgerReason, WalletResponse
from app.models.orm_models import Plan, TokenLedger, User

logger = logging.getLogger(__name__)


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Coerce a DB datetime to UTC-aware.

    SQL Server DATETIME2 columns come back naive; we store UTC (SYSUTCDATETIME),
    so a naive value is interpreted as UTC. Aware values are returned unchanged.
    """
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


class LedgerStatus(str, Enum):
    """Outcome of an ``apply_ledger`` call."""

    APPLIED = "applied"          # the balance changed and a ledger row was written
    DUPLICATE = "duplicate"      # the idempotency key already existed → no-op
    INSUFFICIENT = "insufficient"  # debit would drive the balance negative
    USER_NOT_FOUND = "user_not_found"  # no Users row for the given id


@dataclass
class LedgerOutcome:
    """Result of applying a ledger entry."""

    status: LedgerStatus
    balance_after: Optional[int] = None

    @property
    def ok(self) -> bool:
        """True when the economic effect is in place (applied OR already-applied)."""
        return self.status in (LedgerStatus.APPLIED, LedgerStatus.DUPLICATE)


class _NoApply(Exception):
    """Internal signal: the conditional balance UPDATE matched no row."""


async def apply_ledger(
    db: AsyncSession,
    *,
    user_id: str,
    delta: int,
    reason: str,
    idempotency_key: str,
    ref_type: Optional[str] = None,
    ref_id: Optional[str] = None,
    note: Optional[str] = None,
    created_by: str = "system",
    allow_negative: bool = False,
) -> LedgerOutcome:
    """Atomically change a user's token balance and append a ledger row.

    Args:
        db: Caller-managed session; this function flushes but does not commit.
        user_id: Target user UUID.
        delta: Token change (+credit / -debit).
        reason: A ``LedgerReason`` value.
        idempotency_key: Deterministic per-event key (UNIQUE) — the exactly-once guard.
        ref_type/ref_id: Optional back-reference (e.g. payment / analysis id).
        note: Optional human note.
        created_by: 'system' | 'gateway:<provider>' | admin user id.
        allow_negative: Permit the balance to go below zero (used by refund clawback).

    Returns:
        LedgerOutcome describing whether the entry was applied, was a duplicate,
        the user lacked balance, or the user did not exist.
    """
    # Fast path: a known idempotency key means the effect is already in place.
    existing = await db.execute(
        select(TokenLedger.BalanceAfter).where(
            TokenLedger.IdempotencyKey == idempotency_key
        )
    )
    seen = existing.first()
    if seen is not None:
        return LedgerOutcome(LedgerStatus.DUPLICATE, balance_after=int(seen[0]))

    stmt = update(User).where(User.UserId == user_id)
    if delta < 0 and not allow_negative:
        # Debit guard: only succeeds if it does not drive the balance negative.
        stmt = stmt.where(User.TokenBalance + delta >= 0)
    stmt = stmt.values(TokenBalance=User.TokenBalance + delta).returning(
        User.TokenBalance
    )

    try:
        # SAVEPOINT: isolates a UNIQUE-key collision so the outer transaction
        # survives and the balance UPDATE is undone on the losing racer.
        async with db.begin_nested():
            result = await db.execute(stmt)
            updated = result.first()
            if updated is None:
                raise _NoApply()
            balance_after = int(updated[0])
            db.add(
                TokenLedger(
                    LedgerId=str(uuid4()),
                    UserId=user_id,
                    Delta=delta,
                    BalanceAfter=balance_after,
                    Reason=reason,
                    RefType=ref_type,
                    RefId=ref_id,
                    IdempotencyKey=idempotency_key,
                    Note=note,
                    CreatedBy=created_by,
                    CreatedAt=datetime.now(timezone.utc),
                )
            )
            await db.flush()
        return LedgerOutcome(LedgerStatus.APPLIED, balance_after=balance_after)
    except _NoApply:
        # No row updated: distinguish missing user from insufficient balance.
        exists = await db.execute(select(User.UserId).where(User.UserId == user_id))
        if exists.first() is None:
            return LedgerOutcome(LedgerStatus.USER_NOT_FOUND)
        return LedgerOutcome(LedgerStatus.INSUFFICIENT)
    except IntegrityError:
        # Lost the race on the UNIQUE idempotency key — another caller applied it.
        # The SAVEPOINT rolled back this attempt's balance change already.
        res = await db.execute(
            select(TokenLedger.BalanceAfter).where(
                TokenLedger.IdempotencyKey == idempotency_key
            )
        )
        r = res.first()
        return LedgerOutcome(
            LedgerStatus.DUPLICATE, balance_after=(int(r[0]) if r else None)
        )


def _parse_benefits(benefits_json: Optional[str]) -> dict:
    """Parse a plan's BenefitsJson into a dict, tolerating null / malformed input."""
    if not benefits_json:
        return {}
    try:
        data = json.loads(benefits_json)
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        return {}


def effective_cost(plan: Optional[Plan], plan_active: bool) -> float:
    """Return the per-analysis token cost for a user given their plan.

    A subscription tier may lower the cost via BenefitsJson "cost_per_analysis";
    otherwise the default ``TOKEN_COST_PER_ANALYSIS`` applies. An expired tier
    (``plan_active`` False) falls back to the default.
    """
    default = float(settings.TOKEN_COST_PER_ANALYSIS)
    if plan is None or not plan_active:
        return default
    benefits = _parse_benefits(plan.BenefitsJson)
    raw = benefits.get("cost_per_analysis")
    try:
        cost = float(raw)
    except (TypeError, ValueError):
        return default
    return cost if cost >= 0 else default


async def get_wallet(db: AsyncSession, user_id: str) -> Optional[WalletResponse]:
    """Return the user's wallet snapshot, or None if the user is not in the DB."""
    result = await db.execute(
        select(User.TokenBalance, User.CurrentPlanId, User.PlanExpiresAt).where(
            User.UserId == user_id
        )
    )
    row = result.first()
    if row is None:
        return None
    balance, plan_id, expires_at = row

    plan: Optional[Plan] = None
    plan_code: Optional[str] = None
    if plan_id:
        plan_res = await db.execute(select(Plan).where(Plan.PlanId == plan_id))
        plan = plan_res.scalar_one_or_none()
        plan_code = plan.PlanCode if plan else None

    expires_utc = _as_utc(expires_at)
    plan_active = bool(expires_utc and expires_utc > datetime.now(timezone.utc))
    return WalletResponse(
        token_balance=int(balance or 0),
        current_plan_code=plan_code,
        plan_expires_at=expires_utc,
        cost_per_analysis=effective_cost(plan, plan_active),
    )


async def grant_signup_bonus(db: AsyncSession, user_id: str) -> LedgerOutcome:
    """Credit the one-time signup bonus through the ledger (idempotent per user)."""
    return await apply_ledger(
        db,
        user_id=user_id,
        delta=int(settings.SIGNUP_BONUS_TOKENS),
        reason=LedgerReason.SIGNUP_BONUS,
        idempotency_key=f"signup:{user_id}",
        ref_type="admin",
        created_by="system",
    )


# Reservation outcomes for an analysis charge.
RESERVE_CHARGED = "charged"        # tokens were held — proceed
RESERVE_SKIP = "skip"              # user not in DB (lenient) — proceed unbilled
RESERVE_INSUFFICIENT = "insufficient"  # not enough balance — caller returns 402


async def reserve_analysis(
    db: AsyncSession, user_id: str, request_id: str
) -> Tuple[str, int]:
    """Hold (debit) the per-analysis cost BEFORE the pipeline runs.

    Returns ``(state, cost)`` where state is one of ``RESERVE_*``. Lenient for
    users not present in the DB (test/legacy tokens) — those proceed unbilled,
    matching the persistence layer's behaviour. The caller commits.
    """
    wallet = await get_wallet(db, user_id)
    if wallet is None:
        return (RESERVE_SKIP, 0)
    cost = max(1, math.ceil(wallet.cost_per_analysis))
    outcome = await apply_ledger(
        db,
        user_id=user_id,
        delta=-cost,
        reason=LedgerReason.ANALYSIS_HOLD,
        idempotency_key=f"hold:{request_id}",
        ref_type="analysis",
        ref_id=request_id,
    )
    if outcome.status == LedgerStatus.INSUFFICIENT:
        return (RESERVE_INSUFFICIENT, cost)
    return (RESERVE_CHARGED, cost)


async def refund_analysis(
    db: AsyncSession, user_id: str, request_id: str, cost: int, ratio: float = 1.0
) -> LedgerOutcome:
    """Refund a reserved analysis charge (full on failure, partial on degraded).

    Idempotent per request: keyed ``refund:<request_id>`` so a retry cannot
    refund twice. The caller commits.
    """
    amount = min(cost, max(0, math.ceil(cost * ratio)))
    if amount <= 0:
        return LedgerOutcome(LedgerStatus.DUPLICATE, balance_after=None)
    return await apply_ledger(
        db,
        user_id=user_id,
        delta=amount,
        reason=LedgerReason.ANALYSIS_REFUND,
        idempotency_key=f"refund:{request_id}",
        ref_type="analysis",
        ref_id=request_id,
        allow_negative=True,
    )

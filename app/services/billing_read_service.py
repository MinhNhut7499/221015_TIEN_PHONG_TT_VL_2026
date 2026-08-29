"""Read-only billing queries for the user (plans, ledger, transactions).

Mutations live in ``wallet_service`` (tokens) and ``payment_service`` (orders);
this module only shapes data for display.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing_models import (
    LedgerEntryView,
    LedgerListResponse,
    PlanListResponse,
    PlanView,
    TransactionListResponse,
    TransactionView,
)
from app.models.orm_models import Plan, PaymentTransaction, TokenLedger


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Tag a naive DB datetime as UTC so it serialises with a timezone offset.

    DB DATETIME2 columns come back naive but hold UTC (SYSUTCDATETIME); without
    the offset the frontend's ``new Date()`` misreads them as local time.
    """
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _benefits(raw: Optional[str]) -> Optional[dict]:
    """Parse BenefitsJson for display, tolerating null/malformed values."""
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except (ValueError, TypeError):
        return None


async def list_plans(db: AsyncSession) -> PlanListResponse:
    """Return all active plans, ordered for display."""
    rows = (
        await db.execute(
            select(Plan)
            .where(Plan.IsActive == True)  # noqa: E712 (SQL boolean)
            .order_by(Plan.SortOrder, Plan.PriceAmount)
        )
    ).scalars().all()
    plans = [
        PlanView(
            plan_id=p.PlanId,
            plan_code=p.PlanCode,
            plan_name=p.PlanName,
            plan_type=p.PlanType,
            price_amount=int(p.PriceAmount),
            currency=p.Currency,
            token_amount=int(p.TokenAmount),
            duration_days=p.DurationDays,
            benefits=_benefits(p.BenefitsJson),
            sort_order=p.SortOrder,
        )
        for p in rows
    ]
    return PlanListResponse(total=len(plans), plans=plans)


async def list_ledger(
    db: AsyncSession, user_id: str, *, limit: int = 50, offset: int = 0
) -> LedgerListResponse:
    """Return a page of the user's token-ledger entries, newest first."""
    rows = (
        await db.execute(
            select(TokenLedger)
            .where(TokenLedger.UserId == user_id)
            .order_by(TokenLedger.CreatedAt.desc())
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()
    entries = [
        LedgerEntryView(
            delta=int(r.Delta),
            balance_after=int(r.BalanceAfter),
            reason=r.Reason,
            ref_type=r.RefType,
            ref_id=r.RefId,
            note=r.Note,
            created_at=_utc(r.CreatedAt),
        )
        for r in rows
    ]
    return LedgerListResponse(total=len(entries), entries=entries)


async def list_transactions(
    db: AsyncSession, user_id: str, *, limit: int = 50, offset: int = 0
) -> TransactionListResponse:
    """Return a page of the user's payment transactions, newest first."""
    rows = (
        await db.execute(
            select(PaymentTransaction, Plan.PlanCode)
            .outerjoin(Plan, PaymentTransaction.PlanId == Plan.PlanId)
            .where(PaymentTransaction.UserId == user_id)
            .order_by(PaymentTransaction.CreatedAt.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    txns = [
        TransactionView(
            transaction_id=t.TransactionId,
            order_ref=t.OrderRef,
            provider=t.Provider,
            plan_code=plan_code,
            amount=int(t.Amount),
            currency=t.Currency,
            token_amount=int(t.TokenAmount),
            status=t.Status,
            created_at=_utc(t.CreatedAt),
            paid_at=_utc(t.PaidAt),
        )
        for t, plan_code in rows
    ]
    return TransactionListResponse(total=len(txns), transactions=txns)

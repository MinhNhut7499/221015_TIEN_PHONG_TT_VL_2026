"""Admin billing services: revenue stats, transaction listing, plan CRUD,
and manual token adjustments.

Revenue figures are read from the ``RevenueDaily`` rollup so the dashboard never
scans the full PaymentTransactions table; all money sums cast to BigInteger to
avoid INT overflow.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import List, Optional
from uuid import uuid4

from sqlalchemy import BigInteger, Date, cast, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_billing_models import (
    AdminPlanListResponse,
    AdminPlanView,
    AdminTransactionListResponse,
    AdminTransactionView,
    PlanCreateRequest,
    PlanUpdateRequest,
    RevenueByUserResponse,
    RevenuePoint,
    RevenueStatsResponse,
    TokenAdjustResponse,
    TopSpenderView,
    TopSpendersResponse,
    UserRevenueSeries,
)
from app.models.billing_models import LedgerReason, TxnStatus
from app.models.orm_models import (
    PaymentTransaction,
    Plan,
    Refund,
    RevenueDaily,
    User,
)
from app.services import wallet_service
from app.services.wallet_service import LedgerStatus


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Tag a naive DB datetime (UTC) with tzinfo so it serialises with an offset."""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _bucket_key(d: date, granularity: str) -> str:
    """Map a date to its time-bucket key for the requested granularity.

    week → ISO year-week (``YYYY-Www``), month → ``YYYY-MM``, year → ``YYYY``,
    anything else (day) → ``YYYY-MM-DD``.
    """
    if granularity == "year":
        return d.strftime("%Y")
    if granularity == "month":
        return d.strftime("%Y-%m")
    if granularity == "week":
        return d.strftime("%G-W%V")
    return d.strftime("%Y-%m-%d")


def _benefits(raw: Optional[str]) -> Optional[dict]:
    """Parse a plan's BenefitsJson, tolerating null/malformed values."""
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except (ValueError, TypeError):
        return None


async def get_revenue_stats(
    db: AsyncSession,
    *,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    granularity: str = "day",
    currency: str = "VND",
) -> RevenueStatsResponse:
    """Aggregate the RevenueDaily rollup into totals + a day/month time series."""
    conditions = [RevenueDaily.Currency == currency]
    if date_from is not None:
        conditions.append(RevenueDaily.RevenueDate >= date_from)
    if date_to is not None:
        conditions.append(RevenueDaily.RevenueDate <= date_to)

    rows = (
        await db.execute(
            select(RevenueDaily).where(*conditions).order_by(RevenueDaily.RevenueDate)
        )
    ).scalars().all()

    # Bucket into the requested granularity.
    buckets: dict[str, RevenuePoint] = {}
    for r in rows:
        key = _bucket_key(r.RevenueDate, granularity)
        pt = buckets.get(key)
        if pt is None:
            buckets[key] = RevenuePoint(
                period=key,
                gross=int(r.GrossAmount),
                refund=int(r.RefundAmount),
                net=int(r.NetAmount),
                txn_count=int(r.TxnCount),
                tokens_sold=int(r.TokensSold),
            )
        else:
            pt.gross += int(r.GrossAmount)
            pt.refund += int(r.RefundAmount)
            pt.net += int(r.NetAmount)
            pt.txn_count += int(r.TxnCount)
            pt.tokens_sold += int(r.TokensSold)

    series = [buckets[k] for k in sorted(buckets)]
    active_subs = (
        await db.execute(
            select(func.count(User.UserId)).where(
                User.PlanExpiresAt.isnot(None),
                # Naive UTC to match the DATETIME2 column (stored via SYSUTCDATETIME).
                User.PlanExpiresAt > datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )
    ).scalar_one()

    return RevenueStatsResponse(
        currency=currency,
        total_gross=sum(p.gross for p in series),
        total_refund=sum(p.refund for p in series),
        total_net=sum(p.net for p in series),
        total_txns=sum(p.txn_count for p in series),
        tokens_sold=sum(p.tokens_sold for p in series),
        active_subscriptions=int(active_subs or 0),
        series=series,
    )


_PAID_STATES = [
    TxnStatus.SUCCEEDED,
    TxnStatus.REFUNDED,
    TxnStatus.PARTIALLY_REFUNDED,
]


def _new_point(period: str) -> RevenuePoint:
    """An empty revenue bucket to accumulate into."""
    return RevenuePoint(period=period, gross=0, refund=0, net=0, txn_count=0, tokens_sold=0)


async def get_user_revenue_series(
    db: AsyncSession,
    *,
    user_ids: List[str],
    granularity: str = "month",
    currency: str = "VND",
) -> RevenueByUserResponse:
    """Per-user revenue time series, computed live from PaymentTransactions.

    RevenueDaily has no user dimension, so this aggregates the source records
    grouped by (user, paid date), buckets them by ``granularity`` in Python, and
    nets out succeeded refunds per user. One series is returned per requested
    user that exists (even with no paid transactions → an empty series).
    """
    ids = [u for u in user_ids if u]
    if not ids:
        return RevenueByUserResponse(currency=currency, granularity=granularity, series=[])

    txn_rows = (
        await db.execute(
            select(
                PaymentTransaction.UserId,
                cast(PaymentTransaction.PaidAt, Date).label("d"),
                func.sum(cast(PaymentTransaction.Amount, BigInteger)),
                func.count(PaymentTransaction.TransactionId),
                func.sum(cast(PaymentTransaction.TokenAmount, BigInteger)),
            )
            .where(
                PaymentTransaction.Status.in_(_PAID_STATES),
                PaymentTransaction.PaidAt.isnot(None),
                PaymentTransaction.Currency == currency,
                PaymentTransaction.UserId.in_(ids),
            )
            .group_by(PaymentTransaction.UserId, cast(PaymentTransaction.PaidAt, Date))
        )
    ).all()

    ref_rows = (
        await db.execute(
            select(
                PaymentTransaction.UserId,
                cast(Refund.CreatedAt, Date),
                func.sum(cast(Refund.Amount, BigInteger)),
            )
            .join(PaymentTransaction, Refund.TransactionId == PaymentTransaction.TransactionId)
            .where(
                Refund.Status == "succeeded",
                PaymentTransaction.Currency == currency,
                PaymentTransaction.UserId.in_(ids),
            )
            .group_by(PaymentTransaction.UserId, cast(Refund.CreatedAt, Date))
        )
    ).all()

    # user_id → {period_key → RevenuePoint}
    by_user: dict[str, dict[str, RevenuePoint]] = {uid: {} for uid in ids}
    for uid, d, gross, cnt, tokens in txn_rows:
        key = _bucket_key(d, granularity)
        pt = by_user.setdefault(uid, {}).setdefault(key, _new_point(key))
        pt.gross += int(gross or 0)
        pt.txn_count += int(cnt or 0)
        pt.tokens_sold += int(tokens or 0)
    for uid, d, refund_amt in ref_rows:
        key = _bucket_key(d, granularity)
        pt = by_user.setdefault(uid, {}).setdefault(key, _new_point(key))
        pt.refund += int(refund_amt or 0)
    for buckets in by_user.values():
        for pt in buckets.values():
            pt.net = pt.gross - pt.refund

    name_rows = (
        await db.execute(
            select(User.UserId, User.Email, User.Name).where(User.UserId.in_(ids))
        )
    ).all()
    names = {uid: (email, name) for uid, email, name in name_rows}

    series = [
        UserRevenueSeries(
            user_id=uid,
            email=names.get(uid, (None, None))[0],
            name=names.get(uid, (None, None))[1],
            points=[by_user[uid][k] for k in sorted(by_user[uid])],
        )
        for uid in ids
        if uid in names
    ]
    series.sort(key=lambda s: (s.name or s.email or "").lower())
    return RevenueByUserResponse(currency=currency, granularity=granularity, series=series)


async def get_top_spenders(
    db: AsyncSession, *, limit: int = 10, currency: str = "VND"
) -> TopSpendersResponse:
    """Rank users by net spend (gross minus succeeded refunds), highest first."""
    rows = (
        await db.execute(
            select(
                PaymentTransaction.UserId,
                User.Email,
                User.Name,
                func.sum(cast(PaymentTransaction.Amount, BigInteger)),
                func.count(PaymentTransaction.TransactionId),
                func.sum(cast(PaymentTransaction.TokenAmount, BigInteger)),
            )
            .join(User, PaymentTransaction.UserId == User.UserId)
            .where(
                PaymentTransaction.Status.in_(_PAID_STATES),
                PaymentTransaction.PaidAt.isnot(None),
                PaymentTransaction.Currency == currency,
            )
            .group_by(PaymentTransaction.UserId, User.Email, User.Name)
        )
    ).all()

    refund_rows = (
        await db.execute(
            select(
                PaymentTransaction.UserId,
                func.sum(cast(Refund.Amount, BigInteger)),
            )
            .join(PaymentTransaction, Refund.TransactionId == PaymentTransaction.TransactionId)
            .where(Refund.Status == "succeeded", PaymentTransaction.Currency == currency)
            .group_by(PaymentTransaction.UserId)
        )
    ).all()
    refunds = {uid: int(amt or 0) for uid, amt in refund_rows}

    ranked = sorted(
        (
            {
                "user_id": uid,
                "email": email,
                "name": name,
                "gross": int(gross or 0),
                "net": int(gross or 0) - refunds.get(uid, 0),
                "cnt": int(cnt or 0),
                "tokens": int(tokens or 0),
            }
            for uid, email, name, gross, cnt, tokens in rows
        ),
        key=lambda r: r["net"],
        reverse=True,
    )[: max(1, limit)]

    spenders = [
        TopSpenderView(
            rank=i + 1,
            user_id=r["user_id"],
            email=r["email"],
            name=r["name"],
            total_spent=r["net"],
            gross_spent=r["gross"],
            txn_count=r["cnt"],
            tokens_purchased=r["tokens"],
        )
        for i, r in enumerate(ranked)
    ]
    return TopSpendersResponse(currency=currency, spenders=spenders)


async def list_transactions(
    db: AsyncSession,
    *,
    status_filter: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> AdminTransactionListResponse:
    """List payment transactions (newest first), with buyer email and plan code."""
    stmt = (
        select(PaymentTransaction, User.Email, Plan.PlanCode)
        .outerjoin(User, PaymentTransaction.UserId == User.UserId)
        .outerjoin(Plan, PaymentTransaction.PlanId == Plan.PlanId)
        .order_by(PaymentTransaction.CreatedAt.desc())
    )
    if status_filter:
        stmt = stmt.where(PaymentTransaction.Status == status_filter)
    rows = (await db.execute(stmt.offset(offset).limit(limit))).all()
    txns = [
        AdminTransactionView(
            transaction_id=t.TransactionId,
            order_ref=t.OrderRef,
            user_id=t.UserId,
            user_email=email,
            provider=t.Provider,
            plan_code=plan_code,
            amount=int(t.Amount),
            currency=t.Currency,
            token_amount=int(t.TokenAmount),
            status=t.Status,
            provider_txn_id=t.ProviderTxnId,
            created_at=_utc(t.CreatedAt),
            paid_at=_utc(t.PaidAt),
        )
        for t, email, plan_code in rows
    ]
    return AdminTransactionListResponse(total=len(txns), transactions=txns)


async def revenue_export_rows(
    db: AsyncSession, *, currency: str = "VND"
) -> List[List[str]]:
    """Return RevenueDaily as CSV rows (header + one row per day)."""
    rows = (
        await db.execute(
            select(RevenueDaily)
            .where(RevenueDaily.Currency == currency)
            .order_by(RevenueDaily.RevenueDate)
        )
    ).scalars().all()
    out: List[List[str]] = [
        ["date", "currency", "gross", "refund", "net", "txn_count", "tokens_sold"]
    ]
    for r in rows:
        out.append(
            [
                r.RevenueDate.isoformat(),
                r.Currency,
                str(int(r.GrossAmount)),
                str(int(r.RefundAmount)),
                str(int(r.NetAmount)),
                str(int(r.TxnCount)),
                str(int(r.TokensSold)),
            ]
        )
    return out


# ── Plan management ──────────────────────────────────────────────────────────
def _to_admin_plan(p: Plan) -> AdminPlanView:
    return AdminPlanView(
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
        is_active=bool(p.IsActive),
    )


async def list_plans_admin(db: AsyncSession) -> AdminPlanListResponse:
    """List ALL plans (including inactive) for management."""
    rows = (
        await db.execute(select(Plan).order_by(Plan.SortOrder, Plan.PriceAmount))
    ).scalars().all()
    plans = [_to_admin_plan(p) for p in rows]
    return AdminPlanListResponse(total=len(plans), plans=plans)


async def create_plan(db: AsyncSession, body: PlanCreateRequest) -> AdminPlanView:
    """Create a new plan."""
    plan = Plan(
        PlanId=str(uuid4()),
        PlanCode=body.plan_code,
        PlanName=body.plan_name,
        PlanType=body.plan_type,
        PriceAmount=body.price_amount,
        Currency=body.currency,
        TokenAmount=body.token_amount,
        DurationDays=body.duration_days,
        BenefitsJson=json.dumps(body.benefits) if body.benefits else None,
        SortOrder=body.sort_order,
        IsActive=True,
        CreatedAt=datetime.now(timezone.utc),
    )
    db.add(plan)
    await db.flush()
    return _to_admin_plan(plan)


async def update_plan(
    db: AsyncSession, plan_id: str, body: PlanUpdateRequest
) -> Optional[AdminPlanView]:
    """Apply a partial update to a plan. Returns None if the plan is missing."""
    plan = (
        await db.execute(select(Plan).where(Plan.PlanId == plan_id))
    ).scalar_one_or_none()
    if plan is None:
        return None
    if body.plan_name is not None:
        plan.PlanName = body.plan_name
    if body.price_amount is not None:
        plan.PriceAmount = body.price_amount
    if body.token_amount is not None:
        plan.TokenAmount = body.token_amount
    if body.duration_days is not None:
        plan.DurationDays = body.duration_days
    if body.benefits is not None:
        plan.BenefitsJson = json.dumps(body.benefits)
    if body.sort_order is not None:
        plan.SortOrder = body.sort_order
    if body.is_active is not None:
        plan.IsActive = body.is_active
    plan.UpdatedAt = datetime.now(timezone.utc)
    await db.flush()
    return _to_admin_plan(plan)


async def deactivate_plan(db: AsyncSession, plan_id: str) -> bool:
    """Soft-delete a plan (set IsActive=0). Never hard-delete (keeps txn refs)."""
    res = await db.execute(
        update(Plan)
        .where(Plan.PlanId == plan_id)
        .values(IsActive=False, UpdatedAt=datetime.now(timezone.utc))
    )
    return res.rowcount == 1


async def adjust_tokens(
    db: AsyncSession, *, user_id: str, delta: int, reason: Optional[str], admin_id: str
) -> TokenAdjustResponse:
    """Manually grant (+) or revoke (-) tokens for a user, recorded in the ledger."""
    ledger_reason = LedgerReason.ADMIN_GRANT if delta >= 0 else LedgerReason.ADMIN_REVOKE
    outcome = await wallet_service.apply_ledger(
        db,
        user_id=user_id,
        delta=delta,
        reason=ledger_reason,
        idempotency_key=f"admin:{uuid4().hex}",
        ref_type="admin",
        note=reason,
        created_by=admin_id,
        allow_negative=True,  # admins may revoke below zero deliberately
    )
    return TokenAdjustResponse(
        user_id=user_id,
        delta=delta,
        balance_after=outcome.balance_after or 0,
        applied=outcome.status in (LedgerStatus.APPLIED, LedgerStatus.DUPLICATE),
    )


async def rebuild_revenue(db: AsyncSession) -> dict:
    """Recompute RevenueDaily from source transactions/refunds (drift repair).

    Authoritative re-derivation used by ``scripts/reconcile_revenue.py`` to catch
    any divergence between the incremental rollup and the underlying records.
    """
    paid_states = [
        TxnStatus.SUCCEEDED,
        TxnStatus.REFUNDED,
        TxnStatus.PARTIALLY_REFUNDED,
    ]
    txn_rows = (
        await db.execute(
            select(
                cast(PaymentTransaction.PaidAt, Date).label("d"),
                PaymentTransaction.Currency,
                func.sum(cast(PaymentTransaction.Amount, BigInteger)),
                func.count(PaymentTransaction.TransactionId),
                func.sum(cast(PaymentTransaction.TokenAmount, BigInteger)),
            )
            .where(
                PaymentTransaction.Status.in_(paid_states),
                PaymentTransaction.PaidAt.isnot(None),
            )
            .group_by(cast(PaymentTransaction.PaidAt, Date), PaymentTransaction.Currency)
        )
    ).all()

    agg: dict[tuple, dict] = {}
    for d, cur, gross, cnt, tokens in txn_rows:
        agg[(d, cur)] = {
            "gross": int(gross or 0),
            "refund": 0,
            "tokens": int(tokens or 0),
            "cnt": int(cnt or 0),
        }

    ref_rows = (
        await db.execute(
            select(
                cast(Refund.CreatedAt, Date),
                PaymentTransaction.Currency,
                func.sum(cast(Refund.Amount, BigInteger)),
            )
            .join(PaymentTransaction, Refund.TransactionId == PaymentTransaction.TransactionId)
            .where(Refund.Status == "succeeded")
            .group_by(cast(Refund.CreatedAt, Date), PaymentTransaction.Currency)
        )
    ).all()
    for d, cur, refund_amt in ref_rows:
        entry = agg.setdefault((d, cur), {"gross": 0, "refund": 0, "tokens": 0, "cnt": 0})
        entry["refund"] += int(refund_amt or 0)

    await db.execute(delete(RevenueDaily))
    now = datetime.now(timezone.utc)
    for (d, cur), v in agg.items():
        db.add(
            RevenueDaily(
                RevenueDate=d,
                Currency=cur,
                GrossAmount=v["gross"],
                RefundAmount=v["refund"],
                NetAmount=v["gross"] - v["refund"],
                TxnCount=v["cnt"],
                TokensSold=v["tokens"],
                UpdatedAt=now,
            )
        )
    await db.flush()
    return {"days_rebuilt": len(agg)}

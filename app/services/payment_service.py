"""Payment orchestration: checkout creation and callback fulfilment.

Correctness rules enforced here:

* **Exactly-once credit.** Fulfilment flips the transaction ``pending →
  succeeded`` with an atomic conditional UPDATE (CAS); only the winner credits,
  and the credit itself is idempotent (``purchase:<txnId>`` ledger key). A
  return-url + IPN race, or a replayed callback, can never double-credit.
* **No tampering.** Before crediting we verify the gateway signature AND
  cross-check merchant code, amount, and transaction-status against the stored
  order.
* **Audit.** Every callback (valid or not) is recorded in PaymentCallbacks;
  successful payments increment the RevenueDaily rollup.

The session transaction boundary is owned by the caller (the router via
``get_db``), so the status flip and the credit commit together.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from sqlalchemy import func

from app.models.billing_models import (
    CheckoutResponse,
    LedgerReason,
    PlanType,
    TransactionStatusResponse,
    TxnStatus,
)
from app.models.orm_models import (
    PaymentCallback,
    PaymentTransaction,
    Plan,
    Refund,
    RevenueDaily,
    User,
)
from app.services import wallet_service
from app.services.payments import CheckoutContext, VerifiedCallback, get_gateway

# Refund lifecycle (Refunds.Status)
_REFUND_SUCCEEDED = "succeeded"
_REFUND_FAILED = "failed"

logger = logging.getLogger(__name__)

_GMT7 = timezone(timedelta(hours=7))


def _now() -> datetime:
    """Current UTC time (DB stores UTC; gateway date fields use GMT+7 internally)."""
    return datetime.now(timezone.utc)


def _gen_order_ref() -> str:
    """Generate a unique, gateway-safe order reference (timestamp + random)."""
    return datetime.now(_GMT7).strftime("%Y%m%d%H%M%S") + uuid4().hex[:8]


def _plan_snapshot(plan: Plan) -> str:
    """Serialise the plan as it was at purchase time (for audit if it changes)."""
    return json.dumps(
        {
            "plan_code": plan.PlanCode,
            "plan_name": plan.PlanName,
            "plan_type": plan.PlanType,
            "price_amount": plan.PriceAmount,
            "currency": plan.Currency,
            "token_amount": plan.TokenAmount,
            "duration_days": plan.DurationDays,
            "benefits_json": plan.BenefitsJson,
        }
    )


def _redirect_for(txn: PaymentTransaction, client_ip: str) -> str:
    """Build the gateway redirect URL for a (pending) transaction."""
    gateway = get_gateway(txn.Provider)
    ctx = CheckoutContext(
        order_ref=txn.OrderRef,
        amount=int(txn.Amount),
        currency=txn.Currency,
        order_info=f"Thanh toan {txn.OrderRef}",
        client_ip=client_ip,
        return_url=settings.VNPAY_RETURN_URL,
    )
    return gateway.create_payment(ctx)


async def create_checkout(
    db: AsyncSession,
    *,
    user_id: str,
    plan_id: str,
    client_ip: str,
    idempotency_key: Optional[str] = None,
) -> CheckoutResponse:
    """Create a pending payment order and return the gateway redirect URL.

    The price and token amount are taken from the DB plan (never the client). A
    repeated submit with the same ``idempotency_key`` returns the existing order
    instead of creating a duplicate.

    Raises:
        ValueError: if the plan is missing or inactive.
    """
    plan = (
        await db.execute(select(Plan).where(Plan.PlanId == plan_id))
    ).scalar_one_or_none()
    if plan is None or not plan.IsActive:
        raise ValueError("invalid_plan")

    if idempotency_key:
        existing = (
            await db.execute(
                select(PaymentTransaction).where(
                    PaymentTransaction.UserId == user_id,
                    PaymentTransaction.IdempotencyKey == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return CheckoutResponse(
                transaction_id=existing.TransactionId,
                order_ref=existing.OrderRef,
                redirect_url=_redirect_for(existing, client_ip),
            )

    now = _now()
    order_ref = _gen_order_ref()
    # SQL Server treats NULL as a single distinct value under a UNIQUE constraint
    # (only one NULL row allowed). Default the idempotency key to the unique
    # OrderRef so every order has a distinct, non-null key.
    txn = PaymentTransaction(
        TransactionId=str(uuid4()),
        UserId=user_id,
        PlanId=plan.PlanId,
        Provider=settings.PAYMENT_DEFAULT_PROVIDER,
        OrderRef=order_ref,
        Amount=int(plan.PriceAmount),
        Currency=plan.Currency,
        TokenAmount=int(plan.TokenAmount),
        PlanSnapshotJson=_plan_snapshot(plan),
        Status=TxnStatus.PENDING,
        IdempotencyKey=idempotency_key or order_ref,
        ClientIp=client_ip,
        CreatedAt=now,
        ExpiresAt=now + timedelta(minutes=settings.PAYMENT_ORDER_TTL_MIN),
    )
    db.add(txn)
    await db.flush()
    return CheckoutResponse(
        transaction_id=txn.TransactionId,
        order_ref=txn.OrderRef,
        redirect_url=_redirect_for(txn, client_ip),
    )


async def _mark_failed(db: AsyncSession, txn: PaymentTransaction, reason: str) -> None:
    """Move a still-pending order to ``failed`` (CAS; ignored if already final)."""
    await db.execute(
        update(PaymentTransaction)
        .where(
            PaymentTransaction.TransactionId == txn.TransactionId,
            PaymentTransaction.Status == TxnStatus.PENDING,
        )
        .values(Status=TxnStatus.FAILED, FailureReason=reason[:255], UpdatedAt=_now())
    )


async def _add_revenue(
    db: AsyncSession,
    *,
    currency: str,
    gross: int = 0,
    refund: int = 0,
    tokens: int = 0,
    txn_count: int = 0,
) -> None:
    """Increment the daily revenue rollup for today (UTC date)."""
    day = _now().date()
    row = await db.get(RevenueDaily, (day, currency))
    if row is None:
        db.add(
            RevenueDaily(
                RevenueDate=day,
                Currency=currency,
                GrossAmount=gross,
                RefundAmount=refund,
                NetAmount=gross - refund,
                TxnCount=txn_count,
                TokensSold=tokens,
                UpdatedAt=_now(),
            )
        )
    else:
        row.GrossAmount += gross
        row.RefundAmount += refund
        row.NetAmount = row.GrossAmount - row.RefundAmount
        row.TxnCount += txn_count
        row.TokensSold += tokens
        row.UpdatedAt = _now()
    await db.flush()


async def _credit_and_activate(db: AsyncSession, txn: PaymentTransaction) -> None:
    """Credit tokens for a just-succeeded order and activate a subscription tier."""
    plan = (
        await db.execute(select(Plan).where(Plan.PlanId == txn.PlanId))
    ).scalar_one_or_none() if txn.PlanId else None

    is_subscription = bool(plan and plan.PlanType == PlanType.SUBSCRIPTION)
    reason = LedgerReason.SUBSCRIPTION_GRANT if is_subscription else LedgerReason.PURCHASE
    await wallet_service.apply_ledger(
        db,
        user_id=txn.UserId,
        delta=int(txn.TokenAmount),
        reason=reason,
        idempotency_key=f"purchase:{txn.TransactionId}",
        ref_type="payment",
        ref_id=txn.TransactionId,
        created_by=f"gateway:{txn.Provider}",
    )
    if is_subscription and plan and plan.DurationDays:
        now = _now()
        await db.execute(
            update(User)
            .where(User.UserId == txn.UserId)
            .values(
                CurrentPlanId=plan.PlanId,
                PlanActivatedAt=now,
                PlanExpiresAt=now + timedelta(days=int(plan.DurationDays)),
            )
        )
    await _add_revenue(
        db,
        currency=txn.Currency,
        gross=int(txn.Amount),
        tokens=int(txn.TokenAmount),
        txn_count=1,
    )


async def _process(
    db: AsyncSession, verified: VerifiedCallback
) -> Tuple[str, Optional[PaymentTransaction]]:
    """Validate a verified callback and fulfil the order. Returns (note, txn)."""
    if not verified.valid:
        return "bad_signature", None
    if not verified.order_ref:
        return "no_order_ref", None

    txn = (
        await db.execute(
            select(PaymentTransaction).where(
                PaymentTransaction.OrderRef == verified.order_ref
            )
        )
    ).scalar_one_or_none()
    if txn is None:
        return "unknown_order", None

    params: Dict[str, str] = verified.params
    if params.get("vnp_TmnCode") and params["vnp_TmnCode"] != settings.VNPAY_TMN_CODE:
        return "tmncode_mismatch", txn
    if verified.amount is not None and int(verified.amount) != int(txn.Amount):
        await _mark_failed(db, txn, "amount_mismatch")
        return "amount_mismatch", txn

    # vnp_TransactionStatus is present on IPN; default to OK for the return-url.
    txn_status_ok = params.get("vnp_TransactionStatus", "00") == "00"
    if not (verified.success and txn_status_ok):
        await _mark_failed(db, txn, f"resp={verified.response_code}")
        return "payment_failed", txn

    # CAS: only the winner of pending→succeeded credits.
    now = _now()
    res = await db.execute(
        update(PaymentTransaction)
        .where(
            PaymentTransaction.TransactionId == txn.TransactionId,
            PaymentTransaction.Status == TxnStatus.PENDING,
        )
        .values(
            Status=TxnStatus.SUCCEEDED,
            ProviderTxnId=verified.provider_txn_id,
            ProviderRespCode=verified.response_code,
            PaidAt=now,
            UpdatedAt=now,
        )
    )
    if res.rowcount != 1:
        return "already_processed", txn  # another caller already fulfilled it

    await _credit_and_activate(db, txn)
    return "credited", txn


async def handle_callback(
    db: AsyncSession, *, provider: str, source: str, params: Dict[str, str]
) -> Tuple[str, Optional[PaymentTransaction], VerifiedCallback]:
    """Verify + fulfil a gateway callback and record it for audit.

    Returns (result_note, transaction, verified). ``source`` is 'ipn'|'return'.
    """
    gateway = get_gateway(provider)
    verified = gateway.verify_callback(params)
    note, txn = await _process(db, verified)
    db.add(
        PaymentCallback(
            CallbackId=str(uuid4()),
            TransactionId=txn.TransactionId if txn else None,
            Provider=provider,
            Source=source,
            RawPayload=verified.raw[:4000],
            SignatureValid=verified.valid,
            ResultNote=note,
            ReceivedAt=_now(),
        )
    )
    await db.flush()
    return note, txn, verified


class RefundError(Exception):
    """Refund could not be applied (validation or gateway failure)."""


async def _refunded_so_far(db: AsyncSession, transaction_id: str) -> int:
    """Total amount already refunded (succeeded refunds) for a transaction."""
    total = (
        await db.execute(
            select(func.coalesce(func.sum(Refund.Amount), 0)).where(
                Refund.TransactionId == transaction_id,
                Refund.Status == _REFUND_SUCCEEDED,
            )
        )
    ).scalar_one()
    return int(total or 0)


async def refund_transaction(
    db: AsyncSession,
    *,
    transaction_id: str,
    amount: Optional[int],
    token_clawback: Optional[int],
    reason: Optional[str],
    admin_id: str,
    manual: bool = False,
) -> Refund:
    """Refund a succeeded transaction (full or partial) and claw back tokens.

    Steps (caller commits): validate remaining refundable amount → create a
    Refund row → (unless ``manual``) call the gateway → on success mark the
    transaction refunded/partially_refunded, claw back tokens via the ledger
    (idempotent ``clawback:<RefundId>``), and decrement the revenue rollup.

    Raises:
        RefundError: if the transaction is not refundable or the gateway fails.
    """
    txn = (
        await db.execute(
            select(PaymentTransaction).where(
                PaymentTransaction.TransactionId == transaction_id
            )
        )
    ).scalar_one_or_none()
    if txn is None:
        raise RefundError("transaction_not_found")
    if txn.Status not in (TxnStatus.SUCCEEDED, TxnStatus.PARTIALLY_REFUNDED):
        raise RefundError("not_refundable")

    already = await _refunded_so_far(db, transaction_id)
    remaining = int(txn.Amount) - already
    refund_amount = remaining if amount is None else int(amount)
    if refund_amount <= 0 or refund_amount > remaining:
        raise RefundError("invalid_amount")

    # Proportional token clawback by default (full refund claws back all tokens).
    if token_clawback is None:
        clawback = (
            int(txn.TokenAmount)
            if refund_amount == int(txn.Amount)
            else round(int(txn.TokenAmount) * refund_amount / int(txn.Amount))
        )
    else:
        clawback = int(token_clawback)

    refund = Refund(
        RefundId=str(uuid4()),
        TransactionId=transaction_id,
        Amount=refund_amount,
        TokenClawback=clawback,
        Status="pending",
        Provider=txn.Provider,
        Reason=reason,
        CreatedBy=admin_id,
        CreatedAt=_now(),
    )
    db.add(refund)
    await db.flush()

    if not manual:
        gateway = get_gateway(txn.Provider)
        result = await gateway.refund(
            order_ref=txn.OrderRef,
            provider_txn_id=txn.ProviderTxnId,
            amount=refund_amount,
            original_amount=int(txn.Amount),
            client_ip=txn.ClientIp or "127.0.0.1",
            created_by=admin_id,
        )
        if not result.success:
            refund.Status = _REFUND_FAILED
            refund.UpdatedAt = _now()
            await db.flush()
            raise RefundError("gateway_refund_failed")
        refund.ProviderRefId = result.provider_txn_id

    refund.Status = _REFUND_SUCCEEDED
    refund.UpdatedAt = _now()

    if clawback > 0:
        await wallet_service.apply_ledger(
            db,
            user_id=txn.UserId,
            delta=-clawback,
            reason=LedgerReason.REFUND_CLAWBACK,
            idempotency_key=f"clawback:{refund.RefundId}",
            ref_type="refund",
            ref_id=refund.RefundId,
            note=reason,
            created_by=admin_id,
            allow_negative=True,  # may go negative if the user already spent tokens
        )

    new_total = already + refund_amount
    txn.Status = (
        TxnStatus.REFUNDED if new_total >= int(txn.Amount) else TxnStatus.PARTIALLY_REFUNDED
    )
    txn.UpdatedAt = _now()
    await _add_revenue(db, currency=txn.Currency, refund=refund_amount)
    await db.flush()
    return refund


async def reconcile_pending(
    db: AsyncSession, *, provider: Optional[str] = None
) -> Dict[str, int]:
    """Resolve expired pending orders by querying the gateway (QueryDr).

    For each pending order past its expiry: ask the gateway for the real status;
    fulfil if paid, otherwise mark expired. Protects against lost IPN/return
    (money taken but tokens never granted). Returns a count summary.
    """
    # Naive UTC to match the DATETIME2 column (stored via _now() → SYSUTCDATETIME).
    now = _now().replace(tzinfo=None)
    stmt = select(PaymentTransaction).where(
        PaymentTransaction.Status == TxnStatus.PENDING,
        PaymentTransaction.ExpiresAt.isnot(None),
        PaymentTransaction.ExpiresAt < now,
    )
    if provider:
        stmt = stmt.where(PaymentTransaction.Provider == provider)
    pending = (await db.execute(stmt)).scalars().all()

    checked = fulfilled = expired = still = 0
    for txn in pending:
        checked += 1
        gateway = get_gateway(txn.Provider)
        try:
            result = await gateway.query_status(
                txn.OrderRef, amount=int(txn.Amount), client_ip=txn.ClientIp or "127.0.0.1"
            )
        except Exception as exc:  # noqa: BLE001 — keep reconciling the rest
            logger.warning("Reconcile query failed for %s: %s", txn.OrderRef, exc)
            still += 1
            continue

        if result.success and (result.amount is None or result.amount == int(txn.Amount)):
            res = await db.execute(
                update(PaymentTransaction)
                .where(
                    PaymentTransaction.TransactionId == txn.TransactionId,
                    PaymentTransaction.Status == TxnStatus.PENDING,
                )
                .values(
                    Status=TxnStatus.SUCCEEDED,
                    ProviderTxnId=result.provider_txn_id,
                    PaidAt=now,
                    UpdatedAt=now,
                )
            )
            if res.rowcount == 1:
                await _credit_and_activate(db, txn)
                fulfilled += 1
        elif result.found and not result.success:
            await _mark_failed(db, txn, "querydr_failed")
            expired += 1
        else:
            await db.execute(
                update(PaymentTransaction)
                .where(
                    PaymentTransaction.TransactionId == txn.TransactionId,
                    PaymentTransaction.Status == TxnStatus.PENDING,
                )
                .values(Status=TxnStatus.EXPIRED, UpdatedAt=now)
            )
            expired += 1
    await db.flush()
    return {
        "checked": checked,
        "fulfilled": fulfilled,
        "expired": expired,
        "still_pending": still,
    }


async def get_status(
    db: AsyncSession, *, user_id: str, order_ref: str
) -> Optional[TransactionStatusResponse]:
    """Return a transaction's status for the owning user (frontend polling)."""
    txn = (
        await db.execute(
            select(PaymentTransaction).where(
                PaymentTransaction.OrderRef == order_ref,
                PaymentTransaction.UserId == user_id,
            )
        )
    ).scalar_one_or_none()
    if txn is None:
        return None
    return TransactionStatusResponse(
        order_ref=txn.OrderRef,
        status=txn.Status,
        token_amount=int(txn.TokenAmount),
    )

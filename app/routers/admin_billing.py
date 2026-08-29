"""Admin billing router — revenue, transactions, plan management, token grants.

Mounted under ``/admin``; every handler requires admin privileges. Thin
orchestration only — logic lives in ``billing_admin_service``.
"""
import csv
import io
from datetime import date
from typing import Annotated, Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import require_admin
from app.models.orm_models import PaymentTransaction
from app.models.admin_billing_models import (
    AdminPlanListResponse,
    AdminPlanView,
    AdminTransactionListResponse,
    PlanCreateRequest,
    PlanUpdateRequest,
    ReconcileResponse,
    RefundRequest,
    RefundResponse,
    RevenueByUserResponse,
    RevenueStatsResponse,
    TokenAdjustRequest,
    TokenAdjustResponse,
    TopSpendersResponse,
)
from app.services import billing_admin_service, payment_service
from app.services.payment_service import RefundError
from app.services.system_log_service import LEVEL_INFO, LEVEL_WARNING, log_event

router = APIRouter()

_Admin = Annotated[Dict[str, Any], Depends(require_admin)]
_DB = Annotated[AsyncSession, Depends(get_db)]


@router.get("/revenue", response_model=RevenueStatsResponse, summary="Revenue overview")
async def get_revenue(
    _: _Admin,
    db: _DB,
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    granularity: str = Query(default="day", pattern="^(day|week|month|year)$"),
    currency: str = Query(default="VND"),
) -> RevenueStatsResponse:
    """Aggregated revenue totals + time series from the daily rollup."""
    return await billing_admin_service.get_revenue_stats(
        db, date_from=date_from, date_to=date_to, granularity=granularity, currency=currency
    )


@router.get(
    "/revenue/by-user",
    response_model=RevenueByUserResponse,
    summary="Per-user revenue time series",
)
async def get_revenue_by_user(
    _: _Admin,
    db: _DB,
    user_ids: str = Query(..., description="Comma-separated user IDs"),
    granularity: str = Query(default="month", pattern="^(day|week|month|year)$"),
    currency: str = Query(default="VND"),
) -> RevenueByUserResponse:
    """Revenue series for each requested user, for the comparison chart."""
    ids = [u.strip() for u in user_ids.split(",") if u.strip()]
    return await billing_admin_service.get_user_revenue_series(
        db, user_ids=ids, granularity=granularity, currency=currency
    )


@router.get(
    "/top-spenders",
    response_model=TopSpendersResponse,
    summary="Top-paying users leaderboard",
)
async def get_top_spenders(
    _: _Admin,
    db: _DB,
    limit: int = Query(default=10, ge=1, le=100),
    currency: str = Query(default="VND"),
) -> TopSpendersResponse:
    """The users who have paid the most (ranked by net spend)."""
    return await billing_admin_service.get_top_spenders(db, limit=limit, currency=currency)


@router.get(
    "/revenue/export", summary="Export daily revenue as CSV"
)
async def export_revenue(
    _: _Admin, db: _DB, currency: str = Query(default="VND")
) -> StreamingResponse:
    """Stream the daily revenue rollup as a CSV file for accounting."""
    rows = await billing_admin_service.revenue_export_rows(db, currency=currency)
    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=revenue.csv"},
    )


@router.get(
    "/transactions",
    response_model=AdminTransactionListResponse,
    summary="List payment transactions",
)
async def list_transactions(
    _: _Admin,
    db: _DB,
    status_filter: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> AdminTransactionListResponse:
    """List payment transactions (optionally filtered by status)."""
    return await billing_admin_service.list_transactions(
        db, status_filter=status_filter, limit=limit, offset=offset
    )


@router.get("/plans", response_model=AdminPlanListResponse, summary="List all plans")
async def list_plans(_: _Admin, db: _DB) -> AdminPlanListResponse:
    """List all plans, including inactive ones, for management."""
    return await billing_admin_service.list_plans_admin(db)


@router.post(
    "/plans",
    response_model=AdminPlanView,
    status_code=status.HTTP_201_CREATED,
    summary="Create a plan",
)
async def create_plan(body: PlanCreateRequest, admin: _Admin, db: _DB) -> AdminPlanView:
    """Create a new token pack or subscription tier."""
    plan = await billing_admin_service.create_plan(db, body)
    await log_event(db, LEVEL_INFO, f"Plan created: {body.plan_code} by {admin.get('sub')}")
    return plan


@router.patch("/plans/{plan_id}", response_model=AdminPlanView, summary="Update a plan")
async def update_plan(
    plan_id: str, body: PlanUpdateRequest, _: _Admin, db: _DB
) -> AdminPlanView:
    """Apply a partial update to a plan (price/tokens/benefits/active)."""
    plan = await billing_admin_service.update_plan(db, plan_id, body)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    return plan


@router.delete("/plans/{plan_id}", summary="Deactivate a plan (soft delete)")
async def deactivate_plan(plan_id: str, _: _Admin, db: _DB) -> Dict[str, bool]:
    """Soft-delete a plan so it is no longer purchasable (kept for history)."""
    ok = await billing_admin_service.deactivate_plan(db, plan_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    return {"deactivated": True}


@router.post(
    "/users/{user_id}/token-adjustment",
    response_model=TokenAdjustResponse,
    summary="Grant or revoke tokens for a user",
)
async def adjust_tokens(
    user_id: str, body: TokenAdjustRequest, admin: _Admin, db: _DB
) -> TokenAdjustResponse:
    """Manually grant (positive) or revoke (negative) a user's tokens."""
    result = await billing_admin_service.adjust_tokens(
        db, user_id=user_id, delta=body.delta, reason=body.reason, admin_id=admin.get("sub", "")
    )
    await log_event(
        db, LEVEL_INFO, f"Token adjust {body.delta} for {user_id} by {admin.get('sub')}"
    )
    return result


@router.post(
    "/transactions/{transaction_id}/refund",
    response_model=RefundResponse,
    summary="Refund a transaction (full or partial)",
)
async def refund_transaction(
    transaction_id: str, body: RefundRequest, admin: _Admin, db: _DB
) -> RefundResponse:
    """Refund a succeeded transaction and claw back the granted tokens."""
    try:
        refund = await payment_service.refund_transaction(
            db,
            transaction_id=transaction_id,
            amount=body.amount,
            token_clawback=body.token_clawback,
            reason=body.reason,
            admin_id=admin.get("sub", ""),
            manual=body.manual,
        )
    except RefundError as exc:
        detail = str(exc)
        code = (
            status.HTTP_404_NOT_FOUND
            if detail == "transaction_not_found"
            else status.HTTP_400_BAD_REQUEST
        )
        await log_event(db, LEVEL_WARNING, f"Refund failed ({detail}): {transaction_id}")
        raise HTTPException(status_code=code, detail=detail)

    # Re-read the transaction's resulting status for the response.
    row = (
        await db.execute(
            select(PaymentTransaction.Status).where(
                PaymentTransaction.TransactionId == transaction_id
            )
        )
    ).scalar_one_or_none()
    txn_status = row or ""
    await log_event(
        db, LEVEL_INFO, f"Refund {refund.Amount} on {transaction_id} by {admin.get('sub')}"
    )
    return RefundResponse(
        refund_id=refund.RefundId,
        transaction_id=transaction_id,
        amount=int(refund.Amount),
        token_clawback=int(refund.TokenClawback),
        status=refund.Status,
        transaction_status=txn_status,
    )


@router.post("/reconcile", response_model=ReconcileResponse, summary="Reconcile pending payments")
async def reconcile(_: _Admin, db: _DB) -> ReconcileResponse:
    """Resolve expired pending orders by querying the gateway (recover lost IPNs)."""
    summary = await payment_service.reconcile_pending(db)
    return ReconcileResponse(**summary)

"""Billing router — plans, wallet, checkout, and gateway callbacks.

User endpoints require a valid JWT. The gateway callback endpoints are PUBLIC by
design (the gateway redirect/IPN carries no JWT) — they are authenticated solely
by the provider's signature, verified inside ``payment_service``.
"""
import logging
from typing import Annotated, Any, Dict
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies.auth import get_current_active_user
from app.models.billing_models import (
    CheckoutRequest,
    CheckoutResponse,
    LedgerListResponse,
    PlanListResponse,
    TransactionListResponse,
    TransactionStatusResponse,
    TxnStatus,
    WalletResponse,
)
from app.services import billing_read_service, payment_service, wallet_service
from app.services.payments import get_gateway

logger = logging.getLogger(__name__)

router = APIRouter()

_CurrentUser = Annotated[Dict[str, Any], Depends(get_current_active_user)]
_DB = Annotated[AsyncSession, Depends(get_db)]


def _client_ip(request: Request) -> str:
    """Best-effort client IP, honouring a reverse proxy's X-Forwarded-For."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


# ── User endpoints ───────────────────────────────────────────────────────────
@router.get("/plans", response_model=PlanListResponse, summary="List purchasable plans")
async def get_plans(_: _CurrentUser, db: _DB) -> PlanListResponse:
    """Return all active token packs and subscription tiers."""
    return await billing_read_service.list_plans(db)


@router.get("/wallet", response_model=WalletResponse, summary="Get token wallet")
async def get_wallet(current_user: _CurrentUser, db: _DB) -> WalletResponse:
    """Return the calling user's balance, current tier, and per-analysis cost."""
    wallet = await wallet_service.get_wallet(db, current_user.get("sub", ""))
    if wallet is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return wallet


@router.get("/ledger", response_model=LedgerListResponse, summary="Token history")
async def get_ledger(
    current_user: _CurrentUser,
    db: _DB,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> LedgerListResponse:
    """Return a page of the user's token-ledger entries."""
    return await billing_read_service.list_ledger(
        db, current_user.get("sub", ""), limit=limit, offset=offset
    )


@router.get(
    "/transactions", response_model=TransactionListResponse, summary="Payment history"
)
async def get_transactions(
    current_user: _CurrentUser,
    db: _DB,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> TransactionListResponse:
    """Return a page of the user's payment transactions."""
    return await billing_read_service.list_transactions(
        db, current_user.get("sub", ""), limit=limit, offset=offset
    )


@router.post("/checkout", response_model=CheckoutResponse, summary="Start a checkout")
async def checkout(
    body: CheckoutRequest,
    current_user: _CurrentUser,
    db: _DB,
    request: Request,
) -> CheckoutResponse:
    """Create a pending order and return the gateway redirect URL.

    Raises:
        HTTPException 400: if the plan is missing or inactive.
    """
    try:
        return await payment_service.create_checkout(
            db,
            user_id=current_user.get("sub", ""),
            plan_id=body.plan_id,
            client_ip=_client_ip(request),
            idempotency_key=body.idempotency_key,
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or inactive plan"
        )


@router.get(
    "/transactions/{order_ref}/status",
    response_model=TransactionStatusResponse,
    summary="Poll an order's status",
)
async def transaction_status(
    order_ref: str, current_user: _CurrentUser, db: _DB
) -> TransactionStatusResponse:
    """Return the status of one of the user's orders (used by the result page)."""
    result = await payment_service.get_status(
        db, user_id=current_user.get("sub", ""), order_ref=order_ref
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return result


# ── Gateway callbacks (PUBLIC — authenticated by signature only) ──────────────
@router.get(
    "/callback/{provider}/ipn",
    summary="Gateway IPN (server-to-server confirmation)",
)
async def gateway_ipn(provider: str, request: Request, db: _DB) -> Dict[str, str]:
    """Authoritative payment confirmation. Verifies, fulfils, and acks the gateway.

    VNPay calls this URL server-to-server with the result in the query string.
    """
    params = dict(request.query_params)
    note, _txn, verified = await payment_service.handle_callback(
        db, provider=provider, source="ipn", params=params
    )
    # VNPay expects a specific ack envelope.
    if not verified.valid:
        return {"RspCode": "97", "Message": "Invalid signature"}
    if note in ("credited", "already_processed"):
        return {"RspCode": "00", "Message": "Confirm Success"}
    if note == "unknown_order":
        return {"RspCode": "01", "Message": "Order not found"}
    if note == "amount_mismatch":
        return {"RspCode": "04", "Message": "Invalid amount"}
    return {"RspCode": "02", "Message": note}


@router.get(
    "/callback/{provider}/return",
    summary="Gateway browser return (redirects to the frontend result page)",
)
async def gateway_return(provider: str, request: Request, db: _DB) -> RedirectResponse:
    """Verify the return signature and redirect the browser to the result page.

    Crediting is the IPN's job; this only fulfils as a fallback when
    ``VNPAY_RETURN_MAY_FULFILL`` is enabled (local demos without a public IPN).
    """
    params = dict(request.query_params)
    order_ref = params.get("vnp_TxnRef", "")

    if settings.VNPAY_RETURN_MAY_FULFILL:
        note, _txn, verified = await payment_service.handle_callback(
            db, provider=provider, source="return", params=params
        )
        ok = verified.valid and note in ("credited", "already_processed")
    else:
        verified = get_gateway(provider).verify_callback(params)
        ok = verified.valid and verified.success

    result = "success" if ok else "failed"
    query = urlencode({"ref": order_ref, "status": result})
    return RedirectResponse(
        url=f"{settings.FRONTEND_BASE_URL}/billing/result?{query}",
        status_code=status.HTTP_302_FOUND,
    )

"""VNPay gateway (sandbox-compatible, API version 2.1.0).

Signing/verification follow VNPay's reference algorithm exactly: parameters are
sorted by key and URL-encoded (``quote_plus``); the HMAC-SHA512 of that exact
query string is the secure hash. The SAME encoded string is used both to build
the payment URL and to verify a callback, so they cannot drift.

Amounts are in VND đồng everywhere in our system; VNPay expects the amount
multiplied by 100, handled only inside this module. Date fields use GMT+7, the
timezone VNPay assumes.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple
from urllib.parse import quote_plus, urlencode

import httpx

from app.config import settings
from app.services.payments.base import (
    CheckoutContext,
    PaymentGateway,
    QueryResult,
    VerifiedCallback,
)

logger = logging.getLogger(__name__)

_GMT7 = timezone(timedelta(hours=7))
_VNP_VERSION = "2.1.0"


def _build_query(params: Dict[str, str]) -> str:
    """Return the canonical sorted, URL-encoded query string used for signing.

    Keys are sorted; both keys and values are ``quote_plus``-encoded. This is the
    exact string VNPay signs, so we use it for the URL query and the HMAC input.
    """
    items: List[Tuple[str, str]] = sorted(params.items())
    return "&".join(f"{quote_plus(k)}={quote_plus(str(v))}" for k, v in items)


def _sign(query: str, secret: str) -> str:
    """Return the HMAC-SHA512 hex digest of ``query`` keyed by the hash secret."""
    return hmac.new(secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha512).hexdigest()


class VnpayGateway(PaymentGateway):
    """VNPay payment gateway implementation."""

    provider = "vnpay"

    def __init__(self) -> None:
        """Read VNPay credentials/endpoints from settings."""
        self._tmn_code = settings.VNPAY_TMN_CODE
        self._secret = settings.VNPAY_HASH_SECRET
        self._pay_url = settings.VNPAY_PAYMENT_URL
        self._api_url = settings.VNPAY_API_URL

    def create_payment(self, ctx: CheckoutContext) -> str:
        """Build a signed VNPay payment URL for the given checkout context."""
        now = datetime.now(_GMT7)
        expire = now + timedelta(minutes=settings.PAYMENT_ORDER_TTL_MIN)
        params: Dict[str, str] = {
            "vnp_Version": _VNP_VERSION,
            "vnp_Command": "pay",
            "vnp_TmnCode": self._tmn_code,
            "vnp_Amount": str(int(ctx.amount) * 100),  # VNPay expects amount × 100
            "vnp_CurrCode": ctx.currency,
            "vnp_TxnRef": ctx.order_ref,
            "vnp_OrderInfo": ctx.order_info,
            "vnp_OrderType": "other",
            "vnp_Locale": "vn",
            "vnp_ReturnUrl": ctx.return_url,
            "vnp_IpAddr": ctx.client_ip or "127.0.0.1",
            "vnp_CreateDate": now.strftime("%Y%m%d%H%M%S"),
            "vnp_ExpireDate": expire.strftime("%Y%m%d%H%M%S"),
        }
        query = _build_query(params)
        secure_hash = _sign(query, self._secret)
        return f"{self._pay_url}?{query}&vnp_SecureHash={secure_hash}"

    def verify_callback(self, params: Dict[str, str]) -> VerifiedCallback:
        """Verify a VNPay callback's signature and extract normalised fields."""
        data = dict(params)
        received_hash = data.pop("vnp_SecureHash", "")
        data.pop("vnp_SecureHashType", None)
        query = _build_query(data)
        expected = _sign(query, self._secret)
        valid = hmac.compare_digest(expected.lower(), str(received_hash).lower())

        amount_raw = data.get("vnp_Amount")
        amount = int(amount_raw) // 100 if amount_raw and str(amount_raw).isdigit() else None
        return VerifiedCallback(
            valid=valid,
            success=data.get("vnp_ResponseCode") == "00",
            order_ref=data.get("vnp_TxnRef"),
            provider_txn_id=data.get("vnp_TransactionNo"),
            amount=amount,
            response_code=data.get("vnp_ResponseCode"),
            params=data,
            raw=urlencode(params),
        )

    async def query_status(self, order_ref: str, *, amount: int, client_ip: str) -> QueryResult:
        """Query VNPay (QueryDr) for a transaction's final status (reconciliation)."""
        now = datetime.now(_GMT7)
        request_id = now.strftime("%Y%m%d%H%M%S") + order_ref[-6:]
        create_date = now.strftime("%Y%m%d%H%M%S")
        # QueryDr signs a fixed-order pipe-joined string (per VNPay spec).
        data = "|".join([
            request_id, _VNP_VERSION, "querydr", self._tmn_code, order_ref,
            create_date, create_date, client_ip or "127.0.0.1",
            f"Query {order_ref}",
        ])
        secure_hash = _sign(data, self._secret)
        body = {
            "vnp_RequestId": request_id,
            "vnp_Version": _VNP_VERSION,
            "vnp_Command": "querydr",
            "vnp_TmnCode": self._tmn_code,
            "vnp_TxnRef": order_ref,
            "vnp_OrderInfo": f"Query {order_ref}",
            "vnp_TransactionDate": create_date,
            "vnp_CreateDate": create_date,
            "vnp_IpAddr": client_ip or "127.0.0.1",
            "vnp_SecureHash": secure_hash,
        }
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(self._api_url, json=body)
            payload = resp.json()
        except Exception as exc:  # network / parse — treat as "not found yet"
            logger.warning("VNPay QueryDr failed for %s: %s", order_ref, exc)
            return QueryResult(found=False, success=False, raw=str(exc))

        resp_code = payload.get("vnp_ResponseCode")
        txn_status = payload.get("vnp_TransactionStatus")
        amt_raw = payload.get("vnp_Amount")
        amt = int(amt_raw) // 100 if amt_raw and str(amt_raw).isdigit() else None
        return QueryResult(
            found=resp_code == "00",
            success=resp_code == "00" and txn_status == "00",
            amount=amt,
            provider_txn_id=payload.get("vnp_TransactionNo"),
            raw=str(payload),
        )

    async def refund(
        self,
        *,
        order_ref: str,
        provider_txn_id: Optional[str],
        amount: int,
        original_amount: int,
        client_ip: str,
        created_by: str,
    ) -> QueryResult:
        """Request a VNPay refund (full or partial) for a paid transaction."""
        now = datetime.now(_GMT7)
        request_id = now.strftime("%Y%m%d%H%M%S") + order_ref[-6:]
        create_date = now.strftime("%Y%m%d%H%M%S")
        txn_type = "02" if amount >= original_amount else "03"  # 02 full / 03 partial
        order_info = f"Refund {order_ref}"
        # Checksum over the spec's fixed-order, pipe-joined fields.
        data = "|".join([
            request_id, _VNP_VERSION, "refund", self._tmn_code, txn_type, order_ref,
            str(int(amount) * 100), provider_txn_id or "", create_date, created_by,
            create_date, client_ip or "127.0.0.1", order_info,
        ])
        secure_hash = _sign(data, self._secret)
        body = {
            "vnp_RequestId": request_id,
            "vnp_Version": _VNP_VERSION,
            "vnp_Command": "refund",
            "vnp_TmnCode": self._tmn_code,
            "vnp_TransactionType": txn_type,
            "vnp_TxnRef": order_ref,
            "vnp_Amount": str(int(amount) * 100),
            "vnp_TransactionNo": provider_txn_id or "",
            "vnp_TransactionDate": create_date,
            "vnp_CreateBy": created_by,
            "vnp_CreateDate": create_date,
            "vnp_IpAddr": client_ip or "127.0.0.1",
            "vnp_OrderInfo": order_info,
            "vnp_SecureHash": secure_hash,
        }
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(self._api_url, json=body)
            payload = resp.json()
        except Exception as exc:  # network / parse
            logger.warning("VNPay refund failed for %s: %s", order_ref, exc)
            return QueryResult(found=False, success=False, raw=str(exc))
        return QueryResult(
            found=True,
            success=payload.get("vnp_ResponseCode") == "00",
            provider_txn_id=payload.get("vnp_TransactionNo"),
            raw=str(payload),
        )

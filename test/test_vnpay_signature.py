"""Tests for VNPay signing/verification — the integration's #1 failure point.

Black-box roundtrip: a URL produced by ``create_payment`` must verify; tampering
any field must break the signature; the amount must be un-scaled (÷100).
"""
from urllib.parse import parse_qsl, urlsplit

import pytest

from app.services.payments.vnpay import VnpayGateway
from app.services.payments.base import CheckoutContext


@pytest.fixture
def gateway(monkeypatch):
    """A VnpayGateway with deterministic test credentials."""
    from app.services.payments import vnpay as vnpay_mod

    monkeypatch.setattr(vnpay_mod.settings, "VNPAY_TMN_CODE", "TESTTMN", raising=False)
    monkeypatch.setattr(
        vnpay_mod.settings, "VNPAY_HASH_SECRET", "secretkey1234567890", raising=False
    )
    monkeypatch.setattr(
        vnpay_mod.settings,
        "VNPAY_PAYMENT_URL",
        "https://sandbox.vnpayment.vn/paymentv2/vpcpay.html",
        raising=False,
    )
    return VnpayGateway()


def _url_params(url: str) -> dict:
    """Parse a payment URL's query string into a dict (decoded values)."""
    return dict(parse_qsl(urlsplit(url).query, keep_blank_values=True))


def test_create_payment_url_roundtrips_to_valid_signature(gateway):
    ctx = CheckoutContext(
        order_ref="ORDER123",
        amount=20000,
        currency="VND",
        order_info="Thanh toan goi pack_100",
        client_ip="1.2.3.4",
        return_url="http://localhost:8000/billing/callback/vnpay/return",
    )
    url = gateway.create_payment(ctx)
    params = _url_params(url)

    assert params["vnp_Amount"] == "2000000"  # 20000 × 100
    assert params["vnp_TxnRef"] == "ORDER123"
    assert "vnp_SecureHash" in params

    verified = gateway.verify_callback(params)
    assert verified.valid is True
    assert verified.order_ref == "ORDER123"
    assert verified.amount == 20000  # un-scaled back to đồng


def test_tampered_amount_fails_verification(gateway):
    ctx = CheckoutContext(
        order_ref="ORDER999",
        amount=20000,
        currency="VND",
        order_info="x",
        client_ip="1.2.3.4",
        return_url="http://localhost:8000/r",
    )
    params = _url_params(gateway.create_payment(ctx))
    params["vnp_Amount"] = "100"  # attacker lowers the price
    assert gateway.verify_callback(params).valid is False


def test_success_flag_reads_response_code(gateway):
    ctx = CheckoutContext(
        order_ref="ORD",
        amount=1000,
        currency="VND",
        order_info="x",
        client_ip="1.2.3.4",
        return_url="http://localhost:8000/r",
    )
    params = _url_params(gateway.create_payment(ctx))
    # Re-sign with a response code so the signature stays valid for the assertion.
    from app.services.payments.vnpay import _build_query, _sign

    params["vnp_ResponseCode"] = "00"
    params["vnp_TransactionNo"] = "987654"
    unsigned = {k: v for k, v in params.items() if k != "vnp_SecureHash"}
    params["vnp_SecureHash"] = _sign(_build_query(unsigned), "secretkey1234567890")

    verified = gateway.verify_callback(params)
    assert verified.valid is True
    assert verified.success is True
    assert verified.provider_txn_id == "987654"

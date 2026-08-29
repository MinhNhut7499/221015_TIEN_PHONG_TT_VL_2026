"""Opt-in integration test: a payment is credited exactly once (real SQL Server).

Validates the return-url/IPN + replay race guard: fulfilling the same valid
callback twice credits tokens once (CAS winner + idempotent ledger). Runs only
when RUN_DB_INTEGRATION=1.

Run:  RUN_DB_INTEGRATION=1 pytest test/integration/test_payment_integration.py -v
"""
import asyncio
import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal, engine
from app.models.orm_models import (
    PaymentCallback,
    PaymentTransaction,
    Plan,
    Role,
    TokenLedger,
    User,
)
from app.services import payment_service
from app.services.payments import factory, vnpay
from app.services.payments.vnpay import VnpayGateway, _build_query, _sign

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_INTEGRATION") != "1",
    reason="set RUN_DB_INTEGRATION=1 to run payment money-path tests against the real DB",
)


def _arun(coro_fn):
    """Run an async test body, disposing the engine so the next asyncio.run()
    (a new event loop) does not reuse pooled connections from the closed loop."""
    async def _wrapper():
        try:
            return await coro_fn()
        finally:
            await engine.dispose()

    asyncio.run(_wrapper())

_SECRET = "secretkey1234567890"
_TMN = "TESTTMN"


def _configure(monkeypatch=None):
    """Point the VNPay gateway at deterministic test credentials."""
    vnpay.settings.VNPAY_HASH_SECRET = _SECRET
    vnpay.settings.VNPAY_TMN_CODE = _TMN
    payment_service.settings.VNPAY_TMN_CODE = _TMN
    factory.get_gateway.cache_clear()


def _signed_ipn(order_ref: str, amount_vnd: int) -> dict:
    """Build a correctly-signed successful VNPay IPN params dict."""
    params = {
        "vnp_TmnCode": _TMN,
        "vnp_Amount": str(amount_vnd * 100),
        "vnp_TxnRef": order_ref,
        "vnp_ResponseCode": "00",
        "vnp_TransactionStatus": "00",
        "vnp_TransactionNo": "555111",
        "vnp_PayDate": "20260101120000",
    }
    params["vnp_SecureHash"] = _sign(_build_query(params), _SECRET)
    return params


async def _seed(s: AsyncSession):
    role = (await s.execute(select(Role).limit(1))).scalar_one_or_none()
    if role is None:
        role = Role(RoleId=str(uuid4()), RoleName="user")
        s.add(role)
        await s.flush()
    uid = str(uuid4())
    pid = str(uuid4())
    s.add(User(UserId=uid, Email=f"pay-{uid}@t.local", Name="Pay", IsActive=True,
               GoogleSub=f"test-{uid}",  # unique: schema's GoogleSub UNIQUE rejects 2nd NULL
               RoleId=role.RoleId, TokenBalance=0, CreatedAt=datetime.now(timezone.utc)))
    s.add(Plan(PlanId=pid, PlanCode=f"test_{uid[:8]}", PlanName="Test Pack",
               PlanType="token_pack", PriceAmount=50000, Currency="VND",
               TokenAmount=100, IsActive=True, CreatedAt=datetime.now(timezone.utc)))
    # Flush so User+Plan exist before the FK-bearing PaymentTransaction is inserted
    # (no ORM relationship links them, so the unit-of-work can't order it itself).
    await s.flush()
    order_ref = "ORD" + uuid4().hex[:10]
    tid = str(uuid4())
    s.add(PaymentTransaction(TransactionId=tid, UserId=uid, PlanId=pid, Provider="vnpay",
                             OrderRef=order_ref, Amount=50000, Currency="VND",
                             TokenAmount=100, Status="pending",
                             CreatedAt=datetime.now(timezone.utc)))
    await s.commit()
    return uid, pid, tid, order_ref


async def _cleanup(uid, pid, tid, order_ref):
    async with AsyncSessionLocal() as s:
        await s.execute(delete(PaymentCallback).where(PaymentCallback.TransactionId == tid))
        await s.execute(delete(TokenLedger).where(TokenLedger.UserId == uid))
        await s.execute(delete(PaymentTransaction).where(PaymentTransaction.TransactionId == tid))
        await s.execute(delete(User).where(User.UserId == uid))
        await s.execute(delete(Plan).where(Plan.PlanId == pid))
        await s.commit()


def test_double_ipn_credits_once():
    async def run():
        _configure()
        async with AsyncSessionLocal() as s:
            uid, pid, tid, order_ref = await _seed(s)
        try:
            params = _signed_ipn(order_ref, 50000)

            async with AsyncSessionLocal() as s:
                note1, _, _ = await payment_service.handle_callback(
                    s, provider="vnpay", source="ipn", params=params
                )
                await s.commit()
            async with AsyncSessionLocal() as s:
                note2, _, _ = await payment_service.handle_callback(
                    s, provider="vnpay", source="ipn", params=params
                )
                await s.commit()

            assert note1 == "credited"
            assert note2 == "already_processed"

            async with AsyncSessionLocal() as s:
                bal = (await s.execute(
                    select(User.TokenBalance).where(User.UserId == uid)
                )).scalar_one()
                ledger_rows = (await s.execute(
                    select(TokenLedger).where(TokenLedger.UserId == uid)
                )).scalars().all()
            assert bal == 100              # credited exactly once
            assert len(ledger_rows) == 1   # one purchase ledger row
        finally:
            await _cleanup(uid, pid, tid, order_ref)

    _arun(run)

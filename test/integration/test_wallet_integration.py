"""Opt-in integration tests for the money path against a REAL SQL Server.

These validate the guarantees that a mocked session cannot: the conditional
balance UPDATE, the UNIQUE-idempotency-key SAVEPOINT, and concurrent-debit
safety. They run only when RUN_DB_INTEGRATION=1 and a database is configured,
so the default ``pytest test/`` run (mocked DB) stays green.

Run:  RUN_DB_INTEGRATION=1 pytest test/integration/test_wallet_integration.py -v
"""
import asyncio
import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select

from app.database import AsyncSessionLocal, engine
from app.models.orm_models import Role, TokenLedger, User
from app.services import wallet_service
from app.services.wallet_service import LedgerStatus

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_INTEGRATION") != "1",
    reason="set RUN_DB_INTEGRATION=1 to run money-path tests against the real DB",
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


async def _make_user() -> str:
    """Create a throwaway user with balance 0 and return its id."""
    async with AsyncSessionLocal() as s:
        role = (await s.execute(select(Role).limit(1))).scalar_one_or_none()
        if role is None:
            role = Role(RoleId=str(uuid4()), RoleName="user")
            s.add(role)
            await s.flush()
        uid = str(uuid4())
        s.add(
            User(
                UserId=uid,
                Email=f"wallet-{uid}@test.local",
                Name="Wallet Test",
                # Unique GoogleSub: the schema's GoogleSub UNIQUE allows only one
                # NULL row, so test users must carry a distinct non-null value.
                GoogleSub=f"test-{uid}",
                IsActive=True,
                RoleId=role.RoleId,
                TokenBalance=0,
                CreatedAt=datetime.now(timezone.utc),
            )
        )
        await s.commit()
        return uid


async def _cleanup(uid: str) -> None:
    async with AsyncSessionLocal() as s:
        await s.execute(delete(TokenLedger).where(TokenLedger.UserId == uid))
        await s.execute(delete(User).where(User.UserId == uid))
        await s.commit()


async def _balance(uid: str) -> int:
    async with AsyncSessionLocal() as s:
        return int(
            (await s.execute(select(User.TokenBalance).where(User.UserId == uid)))
            .scalar_one()
        )


async def _ledger_sum(uid: str) -> int:
    async with AsyncSessionLocal() as s:
        total = (
            await s.execute(
                select(func.coalesce(func.sum(TokenLedger.Delta), 0)).where(
                    TokenLedger.UserId == uid
                )
            )
        ).scalar_one()
        return int(total)


def test_credit_then_debit_and_invariant():
    async def run():
        uid = await _make_user()
        try:
            async with AsyncSessionLocal() as s:
                r = await wallet_service.apply_ledger(
                    s, user_id=uid, delta=100, reason="purchase",
                    idempotency_key=f"purchase:{uid}",
                )
                await s.commit()
            assert r.status == LedgerStatus.APPLIED and r.balance_after == 100

            async with AsyncSessionLocal() as s:
                r = await wallet_service.apply_ledger(
                    s, user_id=uid, delta=-30, reason="analysis_hold",
                    idempotency_key=f"hold:{uid}:1",
                )
                await s.commit()
            assert r.status == LedgerStatus.APPLIED and r.balance_after == 70

            assert await _balance(uid) == 70
            assert await _balance(uid) == await _ledger_sum(uid)  # invariant
        finally:
            await _cleanup(uid)

    _arun(run)


def test_insufficient_balance_is_rejected():
    async def run():
        uid = await _make_user()
        try:
            async with AsyncSessionLocal() as s:
                r = await wallet_service.apply_ledger(
                    s, user_id=uid, delta=-5, reason="analysis_hold",
                    idempotency_key=f"hold:{uid}:x",
                )
                await s.commit()
            assert r.status == LedgerStatus.INSUFFICIENT
            assert await _balance(uid) == 0  # unchanged
        finally:
            await _cleanup(uid)

    _arun(run)


def test_duplicate_idempotency_key_is_noop():
    async def run():
        uid = await _make_user()
        try:
            key = f"purchase:{uid}"
            async with AsyncSessionLocal() as s:
                await wallet_service.apply_ledger(
                    s, user_id=uid, delta=50, reason="purchase", idempotency_key=key
                )
                await s.commit()
            # Second apply with the SAME key must not credit again.
            async with AsyncSessionLocal() as s:
                r = await wallet_service.apply_ledger(
                    s, user_id=uid, delta=50, reason="purchase", idempotency_key=key
                )
                await s.commit()
            assert r.status == LedgerStatus.DUPLICATE
            assert await _balance(uid) == 50  # credited exactly once
        finally:
            await _cleanup(uid)

    _arun(run)


def test_concurrent_debit_only_one_wins():
    """Two concurrent debits of the whole balance: exactly one succeeds."""
    async def run():
        uid = await _make_user()
        try:
            async with AsyncSessionLocal() as s:
                await wallet_service.apply_ledger(
                    s, user_id=uid, delta=10, reason="purchase",
                    idempotency_key=f"purchase:{uid}",
                )
                await s.commit()

            async def debit(tag: str):
                async with AsyncSessionLocal() as s:
                    r = await wallet_service.apply_ledger(
                        s, user_id=uid, delta=-10, reason="analysis_hold",
                        idempotency_key=f"hold:{uid}:{tag}",
                    )
                    await s.commit()
                    return r.status

            results = await asyncio.gather(debit("a"), debit("b"))
            applied = [s for s in results if s == LedgerStatus.APPLIED]
            insufficient = [s for s in results if s == LedgerStatus.INSUFFICIENT]
            assert len(applied) == 1 and len(insufficient) == 1
            assert await _balance(uid) == 0
            assert await _balance(uid) == await _ledger_sum(uid)
        finally:
            await _cleanup(uid)

    _arun(run)

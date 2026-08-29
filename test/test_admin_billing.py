"""Endpoint tests for the admin billing routes (mocked DB)."""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.security.security import create_access_token


@pytest.fixture
def admin_token() -> str:
    return create_access_token(
        {"sub": "admin-1", "email": "admin@test.com", "role": "admin"}
    )


@pytest.fixture
def user_token() -> str:
    return create_access_token(
        {"sub": "user-1", "email": "user@test.com", "role": "user"}
    )


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_revenue_requires_admin(user_token: str) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.get("/admin/revenue", headers=_h(user_token))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_revenue_empty_rollup(admin_token: str) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.get("/admin/revenue", headers=_h(admin_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_gross"] == 0
    assert body["series"] == []
    assert body["currency"] == "VND"


@pytest.mark.asyncio
async def test_revenue_accepts_week_granularity(admin_token: str) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.get("/admin/revenue?granularity=week", headers=_h(admin_token))
    assert resp.status_code == 200
    assert resp.json()["series"] == []


@pytest.mark.asyncio
async def test_revenue_by_user_requires_admin(user_token: str) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.get("/admin/revenue/by-user?user_ids=u1,u2", headers=_h(user_token))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_revenue_by_user_empty(admin_token: str) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.get(
            "/admin/revenue/by-user?user_ids=u1,u2&granularity=month",
            headers=_h(admin_token),
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["granularity"] == "month"
    assert body["series"] == []


@pytest.mark.asyncio
async def test_top_spenders_requires_admin(user_token: str) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.get("/admin/top-spenders", headers=_h(user_token))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_top_spenders_empty(admin_token: str) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.get("/admin/top-spenders?limit=5", headers=_h(admin_token))
    assert resp.status_code == 200
    assert resp.json() == {"currency": "VND", "spenders": []}


@pytest.mark.asyncio
async def test_admin_plans_list(admin_token: str) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.get("/admin/plans", headers=_h(admin_token))
    assert resp.status_code == 200
    assert resp.json() == {"total": 0, "plans": []}


@pytest.mark.asyncio
async def test_admin_transactions_list(admin_token: str) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.get("/admin/transactions", headers=_h(admin_token))
    assert resp.status_code == 200
    assert resp.json() == {"total": 0, "transactions": []}


@pytest.mark.asyncio
async def test_revenue_export_csv(admin_token: str) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.get("/admin/revenue/export", headers=_h(admin_token))
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "date,currency,gross" in resp.text


@pytest.mark.asyncio
async def test_refund_unknown_transaction_returns_404(admin_token: str) -> None:
    # No matching transaction under the mock → RefundError → 404.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.post(
            "/admin/transactions/nope/refund",
            json={"manual": True, "reason": "test"},
            headers=_h(admin_token),
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_refund_requires_admin(user_token: str) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.post(
            "/admin/transactions/x/refund", json={"manual": True}, headers=_h(user_token)
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_reconcile_empty(admin_token: str) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.post("/admin/reconcile", headers=_h(admin_token))
    assert resp.status_code == 200
    assert resp.json() == {
        "checked": 0,
        "fulfilled": 0,
        "expired": 0,
        "still_pending": 0,
    }

"""Endpoint tests for the billing layer (mocked DB).

Covers auth guards, empty reads, checkout validation, and the analyze 402 path
when the wallet is out of tokens. Atomic wallet/payment guarantees are covered
by the opt-in integration tests (test/integration/*).
"""
import io

import pytest
from PIL import Image
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.security.security import create_access_token
from app.services import wallet_service


@pytest.fixture
def user_token() -> str:
    """Valid JWT for a regular user."""
    return create_access_token(
        {"sub": "user-uid-001", "email": "user@test.com", "role": "user"}
    )


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), (100, 150, 200)).save(buf, format="JPEG")
    return buf.getvalue()


# ── Auth guards ──────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_billing_plans_requires_auth() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.get("/billing/plans")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_wallet_requires_auth() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.get("/billing/wallet")
    assert resp.status_code == 403


# ── Reads under the mocked (empty) DB ────────────────────────────────────────
@pytest.mark.asyncio
async def test_plans_empty_under_mock_db(user_token: str) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.get("/billing/plans", headers=_headers(user_token))
    assert resp.status_code == 200
    assert resp.json() == {"total": 0, "plans": []}


@pytest.mark.asyncio
async def test_wallet_404_when_user_not_in_db(user_token: str) -> None:
    # The mocked DB has no Users row → get_wallet returns None → 404.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.get("/billing/wallet", headers=_headers(user_token))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_checkout_invalid_plan_returns_400(user_token: str) -> None:
    # No matching Plan row under the mock → create_checkout raises → 400.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.post(
            "/billing/checkout", json={"plan_id": "nope"}, headers=_headers(user_token)
        )
    assert resp.status_code == 400


# ── Analyze charging ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_analyze_insufficient_balance_returns_402(
    user_token: str, monkeypatch, tmp_path
) -> None:
    """When billing is on and the wallet is empty, /analyze returns 402 (no LLM)."""
    from app.routers import analyze as analyze_router

    # A real file for read_bytes() before the reservation check.
    img = tmp_path / "x.jpg"
    img.write_bytes(_make_jpeg())

    monkeypatch.setattr(analyze_router, "_find_upload_path", lambda _fid: img)
    monkeypatch.setattr(analyze_router, "is_pipeline_configured", lambda: True)
    monkeypatch.setattr(analyze_router.settings, "BILLING_ENABLED", True, raising=False)

    async def _insufficient(_db, _uid, _rid):
        return (wallet_service.RESERVE_INSUFFICIENT, 3)

    monkeypatch.setattr(wallet_service, "reserve_analysis", _insufficient)

    # The orchestrator must NOT be invoked when the wallet is empty.
    def _boom():
        raise AssertionError("pipeline must not run when balance is insufficient")

    monkeypatch.setattr(analyze_router, "get_orchestrator", _boom)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.post(
            "/analyze/", json={"file_id": "x"}, headers=_headers(user_token)
        )
    assert resp.status_code == 402


@pytest.mark.asyncio
async def test_analyze_billing_disabled_skips_wallet(
    user_token: str, monkeypatch, tmp_path
) -> None:
    """With billing off, the wallet is never touched (regression guard)."""
    from app.routers import analyze as analyze_router

    img = tmp_path / "x.jpg"
    img.write_bytes(_make_jpeg())
    monkeypatch.setattr(analyze_router, "_find_upload_path", lambda _fid: img)
    monkeypatch.setattr(analyze_router, "is_pipeline_configured", lambda: True)
    monkeypatch.setattr(analyze_router.settings, "BILLING_ENABLED", False, raising=False)

    called = {"reserve": False}

    async def _reserve(_db, _uid, _rid):
        called["reserve"] = True
        return (wallet_service.RESERVE_SKIP, 0)

    monkeypatch.setattr(wallet_service, "reserve_analysis", _reserve)

    class _Result:
        style = "Gothic"
        confidence = 0.9
        explanation = "x"
        key_evidence = []
        components = []
        processing_time_ms = 1
        style_distribution = None
        composition_explanation = None
        evidence_per_style = None
        evidence_sheet = None
        evidence_sheet_vi = None
        gradcam_b64 = None
        explanation_vi = None
        key_evidence_vi = None
        composition_explanation_vi = None
        evidence_per_style_vi = None
        degraded = False
        warnings = []
        run_status = "completed"
        certainty_margin = None
        distribution_entropy = None
        uncertain = False
        candidates = []
        panel_verdicts = []
        panel_agreement = None
        hybrid = False
        extraction_agreement = None
        agent_runs = []

    class _Orch:
        async def analyze(self, _bytes):
            return _Result()

    monkeypatch.setattr(analyze_router, "get_orchestrator", lambda: _Orch())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.post(
            "/analyze/", json={"file_id": "x"}, headers=_headers(user_token)
        )
    assert resp.status_code == 200
    assert called["reserve"] is False  # wallet untouched when billing disabled

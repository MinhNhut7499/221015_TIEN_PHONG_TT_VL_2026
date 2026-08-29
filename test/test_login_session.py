"""Tests for the hybrid mobile app login (Cloud-Sync Polling) flow.

Run with: pytest test/ -v

Covers:
- Endpoint UUID v4 validation (400 on bad / non-v4 ids).
- Poll status pass-through (pending / completed+tokens / expired).
- One-time use at the service level (completed once, then expired).
- complete_session compare-and-set (only writes a pending, unexpired row).
- Flutter callback rejects a forged/unknown state BEFORE exchanging the code.
"""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services import login_session_service as svc

# A valid UUID v4 and a valid-but-wrong-version (v1) UUID for negative tests.
VALID_V4 = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
VALID_V1 = "00000000-0000-1000-8000-000000000000"


def _result(*, first=None, rowcount=1) -> MagicMock:
    """Build a mock SQLAlchemy Result with a controllable .first()/.rowcount."""
    res = MagicMock()
    res.first.return_value = first
    res.rowcount = rowcount
    return res


# ── Endpoint: validation ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_session_rejects_non_uuid() -> None:
    """POST /auth/login-session with a non-UUID id returns 400."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/auth/login-session", json={"session_id": "nope"})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_create_session_rejects_non_v4_uuid() -> None:
    """A syntactically valid but non-v4 UUID is rejected (400)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/auth/login-session", json={"session_id": VALID_V1})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_poll_session_rejects_non_uuid() -> None:
    """GET /auth/login-session/{id} with a non-UUID id returns 400."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/auth/login-session/not-a-uuid")
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_flutter_login_rejects_non_uuid() -> None:
    """GET /auth/google/login/flutter with a non-UUID session_id returns 400."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/auth/google/login/flutter", params={"session_id": "x"})
    assert response.status_code == 400


# ── Endpoint: happy paths ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_session_ok() -> None:
    """POST /auth/login-session with a valid v4 id acknowledges with ok=true."""
    with patch.object(svc, "create_session", new=AsyncMock()) as mock_create:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/auth/login-session", json={"session_id": VALID_V4})
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    mock_create.assert_awaited_once()


@pytest.mark.asyncio
async def test_poll_returns_pending() -> None:
    """Poll returns pending while the app has not finished login."""
    with patch.object(svc, "poll_session", new=AsyncMock(return_value={"status": "pending"})):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(f"/auth/login-session/{VALID_V4}")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending"
    assert body["access_token"] is None


@pytest.mark.asyncio
async def test_poll_returns_completed_with_tokens() -> None:
    """Poll returns the JWT pair once the session is completed."""
    completed = {"status": "completed", "access_token": "AT", "refresh_token": "RT"}
    with patch.object(svc, "poll_session", new=AsyncMock(return_value=completed)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(f"/auth/login-session/{VALID_V4}")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["access_token"] == "AT"
    assert body["refresh_token"] == "RT"


@pytest.mark.asyncio
async def test_flutter_login_redirects_to_google() -> None:
    """The flutter login endpoint 302-redirects to Google with state=session_id."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/auth/google/login/flutter",
            params={"session_id": VALID_V4},
            follow_redirects=False,
        )
    # RedirectResponse defaults to 307 (same as the existing /google/login route).
    assert response.status_code in (302, 307)
    location = response.headers["location"]
    assert "accounts.google.com" in location
    assert f"state={VALID_V4}" in location


# ── Endpoint: flutter callback security ───────────────────────────────────────

@pytest.mark.asyncio
async def test_callback_forged_state_does_not_exchange_code() -> None:
    """A callback whose state is not a pending session must NOT exchange the code."""
    with patch.object(svc, "session_is_pending", new=AsyncMock(return_value=False)), patch(
        "app.routers.auth._exchange_code_for_user_info", new=AsyncMock()
    ) as mock_exchange:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/auth/google/callback/flutter",
                params={"code": "abc", "state": VALID_V4},
            )
    assert response.status_code == 400
    mock_exchange.assert_not_awaited()


@pytest.mark.asyncio
async def test_callback_invalid_uuid_state_rejected() -> None:
    """A callback with a non-UUID state is rejected without touching Google."""
    with patch("app.routers.auth._exchange_code_for_user_info", new=AsyncMock()) as mock_exchange:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/auth/google/callback/flutter",
                params={"code": "abc", "state": "garbage"},
            )
    assert response.status_code == 400
    mock_exchange.assert_not_awaited()


@pytest.mark.asyncio
async def test_callback_completed_when_session_valid() -> None:
    """A valid pending session completes and stores the token (success page)."""
    from app.routers.auth import GoogleUserInfo

    profile = GoogleUserInfo(sub="g-sub", email="u@test.com", name="U", picture="")
    with patch.object(svc, "session_is_pending", new=AsyncMock(return_value=True)), patch(
        "app.routers.auth._exchange_code_for_user_info", new=AsyncMock(return_value=profile)
    ), patch(
        "app.routers.auth._upsert_user", new=AsyncMock(return_value=("uid-1", "user", True))
    ), patch.object(
        svc, "complete_session", new=AsyncMock(return_value=True)
    ) as mock_complete:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/auth/google/callback/flutter",
                params={"code": "abc", "state": VALID_V4},
            )
    assert response.status_code == 200
    assert "thành công" in response.text.lower()
    mock_complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_callback_expired_midway_shows_error_page() -> None:
    """If the session expires between pre-check and CAS, no token page is shown."""
    from app.routers.auth import GoogleUserInfo

    profile = GoogleUserInfo(sub="g-sub", email="u@test.com", name="U", picture="")
    with patch.object(svc, "session_is_pending", new=AsyncMock(return_value=True)), patch(
        "app.routers.auth._exchange_code_for_user_info", new=AsyncMock(return_value=profile)
    ), patch(
        "app.routers.auth._upsert_user", new=AsyncMock(return_value=("uid-1", "user", True))
    ), patch.object(svc, "complete_session", new=AsyncMock(return_value=False)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/auth/google/callback/flutter",
                params={"code": "abc", "state": VALID_V4},
            )
    assert response.status_code == 200
    assert "hết hạn" in response.text.lower()


# ── Service: compare-and-set + one-time use ───────────────────────────────────

@pytest.mark.asyncio
async def test_complete_session_true_when_pending_row_updated() -> None:
    """complete_session returns True when the CAS update affects one row."""
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_result(rowcount=1))
    ok = await svc.complete_session(session, VALID_V4, "AT", "RT", "uid-1")
    assert ok is True


@pytest.mark.asyncio
async def test_complete_session_false_when_no_pending_row() -> None:
    """complete_session returns False (no create/overwrite) when CAS matches nothing."""
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_result(rowcount=0))
    ok = await svc.complete_session(session, VALID_V4, "AT", "RT", "uid-1")
    assert ok is False


@pytest.mark.asyncio
async def test_poll_session_one_time_then_expired() -> None:
    """First poll claims the token; the second finds the row gone (expired)."""
    session = AsyncMock()
    # Poll 1: the atomic DELETE...OUTPUT returns the token row.
    poll1_claim = _result(first=("AT", "RT"))
    # Poll 2: claim returns nothing, and the follow-up SELECT finds no row.
    poll2_claim = _result(first=None)
    poll2_select = _result(first=None)
    session.execute = AsyncMock(side_effect=[poll1_claim, poll2_claim, poll2_select])

    first = await svc.poll_session(session, VALID_V4)
    assert first == {"status": "completed", "access_token": "AT", "refresh_token": "RT"}

    second = await svc.poll_session(session, VALID_V4)
    assert second["status"] == "expired"


@pytest.mark.asyncio
async def test_poll_session_pending() -> None:
    """A still-pending, unexpired session reports pending without a token."""
    session = AsyncMock()
    future = datetime.utcnow() + timedelta(minutes=5)
    claim = _result(first=None)
    select = _result(first=("pending", future))
    session.execute = AsyncMock(side_effect=[claim, select])
    out = await svc.poll_session(session, VALID_V4)
    assert out == {"status": "pending"}


@pytest.mark.asyncio
async def test_poll_session_expired_row_deleted() -> None:
    """An existing but past-TTL row is deleted and reported expired."""
    session = AsyncMock()
    past = datetime.utcnow() - timedelta(minutes=1)
    claim = _result(first=None)
    select = _result(first=("pending", past))
    delete_res = _result()
    session.execute = AsyncMock(side_effect=[claim, select, delete_res])
    out = await svc.poll_session(session, VALID_V4)
    assert out["status"] == "expired"
    # claim + select + delete = 3 execute calls
    assert session.execute.await_count == 3


@pytest.mark.asyncio
async def test_create_session_inserts_when_no_existing_row() -> None:
    """create_session inserts a fresh row when the update matches nothing."""
    session = AsyncMock()
    cleanup = _result()
    update_res = _result(rowcount=0)  # no existing row to reset
    insert_res = _result()
    session.execute = AsyncMock(side_effect=[cleanup, update_res, insert_res])
    await svc.create_session(session, VALID_V4)
    # cleanup + update + insert = 3 execute calls
    assert session.execute.await_count == 3

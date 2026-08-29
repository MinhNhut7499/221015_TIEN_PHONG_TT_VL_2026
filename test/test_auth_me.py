"""Tests for GET /auth/me — the authenticated user's profile endpoint.

Covers:
- no token            → 403 (HTTPBearer rejects)
- valid token, empty DB → 404 (no matching user row)
- valid token, DB row    → 200 with name/email/picture/role

Uses the autouse ``override_get_db`` fixture from conftest; the happy-path
test overrides ``execute`` to return a fake (User, role_name) row.
"""
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.security.security import create_access_token


@pytest.fixture
def user_token() -> str:
    """Valid JWT for a regular user."""
    return create_access_token(
        {"sub": "user-uid-001", "email": "user@test.com", "name": "Test User", "role": "user"}
    )


@pytest.mark.asyncio
async def test_me_without_token_returns_403() -> None:
    """GET /auth/me without a Bearer token is rejected."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/auth/me")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_me_user_not_in_db_returns_404(user_token: str) -> None:
    """A valid token whose subject is absent from the DB returns 404."""
    headers = {"Authorization": f"Bearer {user_token}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/auth/me", headers=headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_me_returns_profile(user_token: str, override_get_db) -> None:
    """A valid token with a matching DB row returns the profile + wallet fields."""
    fake_user = MagicMock()
    fake_user.Name = "Test User"
    fake_user.Email = "user@test.com"
    fake_user.Picture = "https://example.com/avatar.png"

    # First execute: the get_me User+Role join. Second execute: get_wallet's
    # (balance, plan_id, expires_at) lookup (plan_id None → no further query).
    profile_result = MagicMock()
    profile_result.first.return_value = (fake_user, "user")
    wallet_result = MagicMock()
    wallet_result.first.return_value = (25, None, None)
    override_get_db.execute.side_effect = [profile_result, wallet_result]

    headers = {"Authorization": f"Bearer {user_token}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/auth/me", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Test User"
    assert body["email"] == "user@test.com"
    assert body["picture"] == "https://example.com/avatar.png"
    assert body["role"] == "user"
    assert body["token_balance"] == 25
    assert body["plan_code"] is None

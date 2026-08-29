"""Tests for email/password authentication endpoints.

Covers register, login, forgot-password, and reset-password — happy path plus
one error path each. The autouse ``override_get_db`` fixture (conftest) supplies
a mock AsyncSession; each test sets ``execute.return_value`` to shape the rows
the endpoint sees.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.security.security import (
    create_email_verification_token,
    create_password_reset_token,
    hash_password,
)


def _role_lookup_result() -> MagicMock:
    """Result mock: user not found (new account) + role found."""
    role = MagicMock()
    role.RoleId = "role-uid-1"
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    result.scalar_one.return_value = role
    return result


def _user_obj(password: str = "password123", is_active: bool = True) -> MagicMock:
    """A mock User row with a real bcrypt hash."""
    user = MagicMock()
    user.UserId = "user-uid-1"
    user.Email = "user@test.com"
    user.Name = "Test User"
    user.IsActive = is_active
    user.PasswordHash = hash_password(password)
    return user


async def _post(path: str, body: dict):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(path, json=body)


# ── Register (sends verification, no account yet) ─────────────────────────────

@pytest.mark.asyncio
async def test_register_sends_verification_email(override_get_db, monkeypatch) -> None:
    """A brand-new email triggers a verification email and a generic 200."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = None  # no existing account
    override_get_db.execute.return_value = result
    sender = AsyncMock(return_value=True)
    monkeypatch.setattr("app.routers.auth.send_verification_email", sender)
    res = await _post("/auth/register", {
        "email": "new@test.com", "password": "password123", "name": "New User",
    })
    assert res.status_code == 200
    assert "message" in res.json()
    sender.assert_awaited_once()


@pytest.mark.asyncio
async def test_register_short_password_rejected(override_get_db) -> None:
    """A password shorter than 8 chars fails Pydantic validation (422)."""
    res = await _post("/auth/register", {
        "email": "new@test.com", "password": "short", "name": "New User",
    })
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_register_existing_account_is_generic_no_email(override_get_db, monkeypatch) -> None:
    """An email that already has a password account returns generic 200, no email."""
    existing = MagicMock()
    existing.PasswordHash = hash_password("whatever1")
    result = MagicMock()
    result.scalar_one_or_none.return_value = existing
    override_get_db.execute.return_value = result
    sender = AsyncMock(return_value=True)
    monkeypatch.setattr("app.routers.auth.send_verification_email", sender)
    res = await _post("/auth/register", {
        "email": "user@test.com", "password": "password123", "name": "Dup",
    })
    assert res.status_code == 200
    sender.assert_not_awaited()


# ── Verify email (completes registration) ─────────────────────────────────────

@pytest.mark.asyncio
async def test_verify_email_creates_account_and_returns_tokens(override_get_db) -> None:
    """A valid verification token creates the account and returns a JWT pair."""
    result = _role_lookup_result()  # user not found + role found
    override_get_db.execute.return_value = result
    token = create_email_verification_token(
        "new@test.com", "New User", hash_password("password123")
    )
    res = await _post("/auth/verify-email", {"token": token})
    assert res.status_code == 200
    body = res.json()
    assert body["access_token"] and body["refresh_token"]


@pytest.mark.asyncio
async def test_verify_email_invalid_token_returns_400(override_get_db) -> None:
    """A malformed verification token returns 400."""
    res = await _post("/auth/verify-email", {"token": "not-a-jwt"})
    assert res.status_code == 400


# ── Login ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_success(override_get_db) -> None:
    """Correct email/password returns a JWT pair."""
    result = MagicMock()
    result.first.return_value = (_user_obj("password123"), "user")
    override_get_db.execute.return_value = result
    res = await _post("/auth/login", {"email": "user@test.com", "password": "password123"})
    assert res.status_code == 200
    assert res.json()["access_token"]


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(override_get_db) -> None:
    """A wrong password returns a generic 401."""
    result = MagicMock()
    result.first.return_value = (_user_obj("password123"), "user")
    override_get_db.execute.return_value = result
    res = await _post("/auth/login", {"email": "user@test.com", "password": "wrongpass"})
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_email_returns_401(override_get_db) -> None:
    """An unknown email returns 401 (no account enumeration)."""
    result = MagicMock()
    result.first.return_value = None
    override_get_db.execute.return_value = result
    res = await _post("/auth/login", {"email": "ghost@test.com", "password": "password123"})
    assert res.status_code == 401


# ── Forgot password ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_forgot_password_sends_email_for_known_account(override_get_db, monkeypatch) -> None:
    """A known password account triggers a reset email and a generic 200."""
    user = _user_obj()
    result = MagicMock()
    result.scalar_one_or_none.return_value = user
    override_get_db.execute.return_value = result
    sender = AsyncMock(return_value=True)
    monkeypatch.setattr("app.routers.auth.send_password_reset_email", sender)
    res = await _post("/auth/forgot-password", {"email": "user@test.com"})
    assert res.status_code == 200
    assert "message" in res.json()
    sender.assert_awaited_once()


@pytest.mark.asyncio
async def test_forgot_password_unknown_email_is_generic_200(override_get_db, monkeypatch) -> None:
    """An unknown email returns the same 200 and sends nothing."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    override_get_db.execute.return_value = result
    sender = AsyncMock(return_value=True)
    monkeypatch.setattr("app.routers.auth.send_password_reset_email", sender)
    res = await _post("/auth/forgot-password", {"email": "ghost@test.com"})
    assert res.status_code == 200
    sender.assert_not_awaited()


# ── Reset password ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reset_password_with_valid_token(override_get_db) -> None:
    """A valid reset token updates the password and returns 200."""
    user = _user_obj()
    result = MagicMock()
    result.scalar_one_or_none.return_value = user
    override_get_db.execute.return_value = result
    token = create_password_reset_token("user-uid-1")
    res = await _post("/auth/reset-password", {"token": token, "new_password": "brandnew12"})
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_reset_password_invalid_token_returns_400(override_get_db) -> None:
    """A malformed reset token returns 400."""
    res = await _post("/auth/reset-password", {"token": "not-a-jwt", "new_password": "brandnew12"})
    assert res.status_code == 400

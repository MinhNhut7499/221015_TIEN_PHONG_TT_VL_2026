"""Tests for the website CMS: public read, RBAC, optimistic concurrency.

Run with: pytest test/ -v
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.security.security import create_access_token
from app.services import cms_service


@pytest.fixture
def admin_token() -> str:
    return create_access_token({"sub": "admin-1", "email": "admin@test.com", "role": "admin"})


@pytest.fixture
def user_token() -> str:
    return create_access_token({"sub": "user-1", "email": "user@test.com", "role": "user"})


@pytest.fixture(autouse=True)
def clear_cms_cache():
    """Drop the published-content cache so tests do not leak content."""
    cms_service.invalidate_cache()
    yield
    cms_service.invalidate_cache()


def _scalar_result(value):
    """Build a mock result whose .scalar() returns *value*."""
    result = MagicMock()
    result.scalar.return_value = value
    return result


def _first_result(value):
    """Build a mock result whose .scalars().first() returns *value*."""
    result = MagicMock()
    scalars = MagicMock()
    scalars.first.return_value = value
    result.scalars.return_value = scalars
    return result


# ── Public content endpoint ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_public_content_empty_when_nothing_published() -> None:
    """GET /content/landing returns an empty override when nothing is published."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/content/landing")
    assert res.status_code == 200
    body = res.json()
    assert body["page_key"] == "landing" and body["content"] == {}


@pytest.mark.asyncio
async def test_public_content_unknown_page_400() -> None:
    """An unknown page key is rejected."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/content/bogus")
    assert res.status_code == 400


# ── Admin CMS RBAC ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_draft_user_forbidden(user_token: str) -> None:
    """A non-admin cannot read the CMS draft."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(
            "/admin/cms/landing/draft", headers={"Authorization": f"Bearer {user_token}"}
        )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_draft_admin_ok(admin_token: str) -> None:
    """An admin reads the draft (empty content when none exists)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(
            "/admin/cms/landing/draft", headers={"Authorization": f"Bearer {admin_token}"}
        )
    assert res.status_code == 200
    assert res.json()["has_draft"] is False


# ── Service logic ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_save_draft_stale_base_revision_conflicts() -> None:
    """Saving against an outdated base revision raises 409."""
    session = AsyncMock()
    session.execute.return_value = _scalar_result(5)  # current published revision = 5
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await cms_service.save_draft(session, "landing", {"en": {}}, "admin-1", base_revision_no=2)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_publish_without_draft_returns_400() -> None:
    """Publishing with no draft present raises 400."""
    session = AsyncMock()
    session.execute.return_value = _first_result(None)  # no draft row
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await cms_service.publish(session, "landing", "admin-1")
    assert exc.value.status_code == 400

"""Tests for the knowledge router (GET /knowledge/style).

The knowledge endpoints are read-only over the in-memory style KB; only the
auth dependency touches the DB (mocked by the autouse ``override_get_db``).
"""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.security.security import create_access_token


@pytest.fixture
def user_token() -> str:
    """Valid JWT for a regular user."""
    return create_access_token({"sub": "user-uid-001", "email": "user@test.com", "role": "user"})


@pytest.mark.asyncio
async def test_style_card_by_name(user_token: str) -> None:
    """A known style name resolves to a full card with family + siblings."""
    headers = {"Authorization": f"Bearer {user_token}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/knowledge/style", params={"name": "Gothic"}, headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "gothic"
    assert body["name"]
    assert body["family_name"]
    assert isinstance(body["defining_features"], list) and body["defining_features"]
    # Siblings never include the style itself.
    assert all(s["id"] != "gothic" for s in body["siblings"])


@pytest.mark.asyncio
async def test_style_card_fuzzy_and_alias(user_token: str) -> None:
    """Free-text with noise words ('Gothic architecture') still resolves."""
    headers = {"Authorization": f"Bearer {user_token}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/knowledge/style", params={"name": "Gothic architecture"}, headers=headers
        )
    assert response.status_code == 200
    assert response.json()["id"] == "gothic"


@pytest.mark.asyncio
async def test_style_card_by_id(user_token: str) -> None:
    """Looking up by exact KB id returns the same entry."""
    headers = {"Authorization": f"Bearer {user_token}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/knowledge/style/gothic", headers=headers)
    assert response.status_code == 200
    assert response.json()["id"] == "gothic"


@pytest.mark.asyncio
async def test_unknown_name_returns_404(user_token: str) -> None:
    """A name matching no KB entry returns 404."""
    headers = {"Authorization": f"Bearer {user_token}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/knowledge/style", params={"name": "zzzznotastyle"}, headers=headers
        )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_unknown_id_returns_404(user_token: str) -> None:
    """An unknown KB id returns 404."""
    headers = {"Authorization": f"Bearer {user_token}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/knowledge/style/not-a-real-id", headers=headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_requires_auth() -> None:
    """Missing Bearer token is rejected."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/knowledge/style", params={"name": "Gothic"})
    assert response.status_code in (401, 403)

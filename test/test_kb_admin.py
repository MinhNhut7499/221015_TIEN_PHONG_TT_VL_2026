"""Test suite for the admin Knowledge-Base API (/admin/kb).

Runs against a temporary styles.json so the real KB is never touched. The KB
endpoints do not hit the database, so the autouse db mock in conftest is
irrelevant here — only the admin token guard and file I/O matter.

Run with: pytest test/test_kb_admin.py -v
"""
import json
from pathlib import Path
from typing import Dict

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app
from app.security.security import create_access_token
from app.services import kb_suggestion_store
from chatbot.services.style_kb_service import get_style_kb

_MINI_KB = {
    "schema_version": "1.0",
    "note": "test KB",
    "sources": ["test"],
    "families": {
        "ancient": {"name": "Ancient", "parent": None},
        "islamic": {"name": "Islamic", "parent": None},
    },
    "styles": [
        {
            "id": "ancient-greek", "name": "Ancient Greek", "aliases": ["Hellenic"],
            "parent": "ancient", "region": ["Greece"], "period": "800 BCE-100 BCE",
            "defining_features": ["colonnade"], "expected_profile": {"supports": "Doric"},
            "description": "test", "aat_id": "TBD", "wikidata_id": "TBD", "references": ["AAT"],
        },
        {
            "id": "moorish", "name": "Moorish", "aliases": [],
            "parent": "islamic", "region": ["Iberia"], "period": "750-1492",
            "defining_features": ["horseshoe arches"], "expected_profile": {"arch": "horseshoe"},
            "description": "test", "aat_id": "TBD", "wikidata_id": "TBD", "references": ["AAT"],
        },
    ],
}


@pytest.fixture
def admin_token() -> str:
    """JWT with role=admin."""
    return create_access_token({"sub": "admin-uid-001", "email": "admin@test.com", "role": "admin"})


@pytest.fixture
def user_token() -> str:
    """JWT with role=user."""
    return create_access_token({"sub": "user-uid-001", "email": "user@test.com", "role": "user"})


@pytest.fixture
def temp_kb(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the KB + suggestion store at a temp styles.json and reset caches."""
    kb_file = tmp_path / "styles.json"
    kb_file.write_text(json.dumps(_MINI_KB, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(settings, "STYLE_KB_PATH", str(kb_file))
    get_style_kb.cache_clear()
    yield kb_file
    get_style_kb.cache_clear()


def _hdr(token: str) -> Dict[str, str]:
    """Build a bearer auth header."""
    return {"Authorization": f"Bearer {token}"}


async def _client() -> AsyncClient:
    """Build an ASGI test client."""
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ── Auth guard ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_styles_requires_admin(temp_kb: Path, user_token: str) -> None:
    """A non-admin token is rejected with 403."""
    async with await _client() as client:
        res = await client.get("/admin/kb/styles", headers=_hdr(user_token))
    assert res.status_code == 403


# ── Styles ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_styles(temp_kb: Path, admin_token: str) -> None:
    """List returns every seeded style."""
    async with await _client() as client:
        res = await client.get("/admin/kb/styles", headers=_hdr(admin_token))
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 2
    assert {s["id"] for s in body["styles"]} == {"ancient-greek", "moorish"}


@pytest.mark.asyncio
async def test_get_style_404(temp_kb: Path, admin_token: str) -> None:
    """Unknown style id returns 404."""
    async with await _client() as client:
        res = await client.get("/admin/kb/styles/ghost", headers=_hdr(admin_token))
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_create_style_persists_and_clears_cache(temp_kb: Path, admin_token: str) -> None:
    """Creating a style writes the file and the new entry is immediately visible."""
    payload = {
        "id": "gothic", "name": "Gothic", "aliases": [], "parent": "ancient",
        "region": ["Europe"], "period": "1140-1500", "defining_features": ["pointed arch"],
        "expected_profile": {"arch": "pointed"}, "description": "", "references": [],
    }
    async with await _client() as client:
        res = await client.post("/admin/kb/styles", json=payload, headers=_hdr(admin_token))
        assert res.status_code == 201
        # Visible through the live KB cache right away (cache_clear worked).
        follow = await client.get("/admin/kb/styles/gothic", headers=_hdr(admin_token))
    assert follow.status_code == 200
    on_disk = json.loads(temp_kb.read_text(encoding="utf-8"))
    assert any(s["id"] == "gothic" for s in on_disk["styles"])


@pytest.mark.asyncio
async def test_create_duplicate_id_409(temp_kb: Path, admin_token: str) -> None:
    """Creating a style whose id already exists returns 409."""
    payload = {"id": "moorish", "name": "Dup", "parent": "islamic"}
    async with await _client() as client:
        res = await client.post("/admin/kb/styles", json=payload, headers=_hdr(admin_token))
    assert res.status_code == 409


@pytest.mark.asyncio
async def test_create_unknown_parent_400(temp_kb: Path, admin_token: str) -> None:
    """Creating a style with a non-existent family returns 400."""
    payload = {"id": "newstyle", "name": "New", "parent": "nope"}
    async with await _client() as client:
        res = await client.post("/admin/kb/styles", json=payload, headers=_hdr(admin_token))
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_create_invalid_id_400(temp_kb: Path, admin_token: str) -> None:
    """An id that is not a slug is rejected with 400."""
    payload = {"id": "Not A Slug", "name": "X", "parent": "ancient"}
    async with await _client() as client:
        res = await client.post("/admin/kb/styles", json=payload, headers=_hdr(admin_token))
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_update_style(temp_kb: Path, admin_token: str) -> None:
    """Updating overwrites the entry's fields."""
    payload = {"id": "moorish", "name": "Moorish (edited)", "parent": "islamic",
               "defining_features": ["muqarnas"]}
    async with await _client() as client:
        res = await client.put("/admin/kb/styles/moorish", json=payload, headers=_hdr(admin_token))
    assert res.status_code == 200
    assert res.json()["name"] == "Moorish (edited)"


@pytest.mark.asyncio
async def test_update_missing_404(temp_kb: Path, admin_token: str) -> None:
    """Updating an unknown style returns 404."""
    payload = {"id": "ghost", "name": "Ghost"}
    async with await _client() as client:
        res = await client.put("/admin/kb/styles/ghost", json=payload, headers=_hdr(admin_token))
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_delete_style(temp_kb: Path, admin_token: str) -> None:
    """Deleting removes the entry; deleting again returns 404."""
    async with await _client() as client:
        res = await client.delete("/admin/kb/styles/moorish", headers=_hdr(admin_token))
        assert res.status_code == 200
        again = await client.delete("/admin/kb/styles/moorish", headers=_hdr(admin_token))
    assert again.status_code == 404


# ── Families ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_family_crud(temp_kb: Path, admin_token: str) -> None:
    """Create, rename, and list families."""
    async with await _client() as client:
        created = await client.post(
            "/admin/kb/families", json={"id": "modern", "name": "Modern"}, headers=_hdr(admin_token)
        )
        assert created.status_code == 201
        renamed = await client.put(
            "/admin/kb/families/modern", json={"name": "Modern & Contemporary"},
            headers=_hdr(admin_token),
        )
        assert renamed.status_code == 200
        listing = await client.get("/admin/kb/families", headers=_hdr(admin_token))
    ids = {f["id"] for f in listing.json()["families"]}
    assert {"ancient", "islamic", "modern"} <= ids


@pytest.mark.asyncio
async def test_delete_family_with_styles_409(temp_kb: Path, admin_token: str) -> None:
    """A family still referenced by a style cannot be deleted."""
    async with await _client() as client:
        res = await client.delete("/admin/kb/families/ancient", headers=_hdr(admin_token))
    assert res.status_code == 409


@pytest.mark.asyncio
async def test_delete_empty_family(temp_kb: Path, admin_token: str) -> None:
    """An empty family deletes cleanly."""
    async with await _client() as client:
        await client.post(
            "/admin/kb/families", json={"id": "empty", "name": "Empty"}, headers=_hdr(admin_token)
        )
        res = await client.delete("/admin/kb/families/empty", headers=_hdr(admin_token))
    assert res.status_code == 200


# ── Suggestion queue ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_suggestions_list_and_dismiss(temp_kb: Path, admin_token: str) -> None:
    """Recorded out-of-KB names are listed and can be dismissed."""
    kb_suggestion_store.record(["Streamline Moderne", "Streamline Moderne", "Googie"])
    async with await _client() as client:
        listing = await client.get("/admin/kb/suggestions", headers=_hdr(admin_token))
        assert listing.status_code == 200
        body = listing.json()
        assert body["total"] == 2
        # Most frequent first.
        assert body["suggestions"][0]["name"] == "Streamline Moderne"
        assert body["suggestions"][0]["count"] == 2
        dismissed = await client.delete(
            "/admin/kb/suggestions/Googie", headers=_hdr(admin_token)
        )
        assert dismissed.status_code == 200
        assert dismissed.json()["dismissed"] is True
        after = await client.get("/admin/kb/suggestions", headers=_hdr(admin_token))
    assert after.json()["total"] == 1

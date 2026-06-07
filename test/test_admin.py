"""Test suite for the admin API endpoints.

Run with: pytest test/ -v

Groups:
- Auth guards     : no token → 403, invalid token → 401, user role → 403
- Happy path      : admin token → 200 on all 10 endpoints
- Email fallback  : token without 'role' but email in ADMIN_EMAILS → 200
- Stats accuracy  : temp files → assert total_files and breakdown_by_type
- Stub shape      : empty lists + non-empty 'note' field on all DB stubs
"""
from pathlib import Path
from unittest.mock import PropertyMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app
from app.security.security import create_access_token


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def admin_token() -> str:
    """JWT with role=admin."""
    return create_access_token({"sub": "admin-uid-001", "email": "admin@test.com", "role": "admin"})


@pytest.fixture
def user_token() -> str:
    """JWT with role=user."""
    return create_access_token({"sub": "user-uid-001", "email": "user@test.com", "role": "user"})


@pytest.fixture
def no_role_token() -> str:
    """JWT without role claim — simulates a token issued before role was added."""
    return create_access_token({"sub": "old-uid-001", "email": "old@test.com"})


# ── Auth guard tests ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stats_no_token_returns_403() -> None:
    """GET /admin/stats without any token should return 403."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/admin/stats")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_stats_invalid_token_returns_401() -> None:
    """GET /admin/stats with a malformed token should return 401."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/admin/stats", headers={"Authorization": "Bearer not.a.valid.token"}
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_stats_user_role_returns_403(user_token: str) -> None:
    """GET /admin/stats with a user-role token should return 403."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/admin/stats", headers={"Authorization": f"Bearer {user_token}"}
        )
    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access required"


# ── Happy path: all 10 endpoints ──────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/admin/stats"),
        ("GET", "/admin/files"),
        ("GET", "/admin/users"),
        ("GET", "/admin/projects"),
        ("GET", "/admin/images"),
        ("GET", "/admin/logs"),
        ("GET", "/admin/agents"),
    ],
)
async def test_admin_get_endpoints_return_200(
    method: str, path: str, admin_token: str
) -> None:
    """All admin GET endpoints return 200 with a valid admin token."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.request(
            method, path, headers={"Authorization": f"Bearer {admin_token}"}
        )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_update_user_status_returns_200(admin_token: str) -> None:
    """PATCH /admin/users/{id}/status returns 200 with admin token."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            "/admin/users/some-user-id/status",
            json={"is_active": False},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_delete_project_returns_200(admin_token: str) -> None:
    """DELETE /admin/projects/{id} returns 200 with admin token."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.delete(
            "/admin/projects/some-project-id",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_delete_image_returns_200(admin_token: str) -> None:
    """DELETE /admin/images/{id} returns 200 with admin token."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.delete(
            "/admin/images/some-image-id",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert response.status_code == 200


# ── Email fallback ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_email_fallback_grants_access(no_role_token: str) -> None:
    """Token without role claim passes require_admin when email is in ADMIN_EMAILS."""
    with patch.object(
        type(settings),
        "admin_emails_list",
        new_callable=PropertyMock,
        return_value=["old@test.com"],
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/admin/stats", headers={"Authorization": f"Bearer {no_role_token}"}
            )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_no_role_token_without_email_match_returns_403(no_role_token: str) -> None:
    """Token without role claim and email NOT in ADMIN_EMAILS returns 403."""
    with patch.object(
        type(settings),
        "admin_emails_list",
        new_callable=PropertyMock,
        return_value=[],
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/admin/stats", headers={"Authorization": f"Bearer {no_role_token}"}
            )
    assert response.status_code == 403


# ── Stats accuracy ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stats_counts_files_correctly(
    tmp_path: Path, admin_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GET /admin/stats reflects actual files in the upload directory."""
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    (tmp_path / "aaa.jpg").write_bytes(b"x" * 1024)
    (tmp_path / "bbb.jpg").write_bytes(b"x" * 512)
    (tmp_path / "ccc.png").write_bytes(b"x" * 256)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/admin/stats", headers={"Authorization": f"Bearer {admin_token}"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["total_files"] == 3
    assert body["total_size_bytes"] == 1024 + 512 + 256
    by_type = {b["extension"]: b["count"] for b in body["breakdown_by_type"]}
    assert by_type["jpg"] == 2
    assert by_type["png"] == 1


@pytest.mark.asyncio
async def test_stats_empty_dir_returns_zeros(
    tmp_path: Path, admin_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GET /admin/stats on an empty directory returns all-zero counts."""
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/admin/stats", headers={"Authorization": f"Bearer {admin_token}"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["total_files"] == 0
    assert body["total_size_bytes"] == 0
    assert body["breakdown_by_type"] == []


# ── Stub shape ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path,list_field",
    [
        ("/admin/users", "users"),
        ("/admin/projects", "projects"),
        ("/admin/images", "images"),
        ("/admin/agents", "agents"),
        ("/admin/logs", "logs"),
    ],
)
async def test_db_endpoints_return_empty_list(
    path: str, list_field: str, admin_token: str
) -> None:
    """DB-backed endpoints return an empty list and total=0 when the DB is empty.

    The autouse ``override_get_db`` fixture supplies a session whose ``execute``
    calls return no rows, so each endpoint should report an empty collection.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            path, headers={"Authorization": f"Bearer {admin_token}"}
        )
    assert response.status_code == 200
    body = response.json()
    assert body[list_field] == []
    assert body["total"] == 0
    assert body.get("note") is None, "Phase 3 DB responses must not include the 'note' field"

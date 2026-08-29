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
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app
from app.security.security import create_access_token


def _user_row_result(email: str, role_name: str, rowcount: int = 1) -> MagicMock:
    """Mock result whose .first() returns (email, role_name) with a rowcount."""
    result = MagicMock()
    result.first.return_value = (email, role_name)
    result.rowcount = rowcount
    return result


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
async def test_update_user_status_returns_200(admin_token: str, override_get_db) -> None:
    """PATCH /admin/users/{id}/status returns 200 when target is a regular user."""
    override_get_db.execute.return_value = _user_row_result("u@test.com", "user")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            "/admin/users/some-user-id/status",
            json={"is_active": False},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_update_user_status_blocks_admin(admin_token: str, override_get_db) -> None:
    """Deactivating an admin account is rejected with 400."""
    override_get_db.execute.return_value = _user_row_result("boss@test.com", "admin")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            "/admin/users/admin-user-id/status",
            json={"is_active": False},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_update_user_status_404_when_missing(admin_token: str) -> None:
    """Toggling a non-existent user returns 404 (default empty-DB mock)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            "/admin/users/ghost-id/status",
            json={"is_active": False},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert response.status_code == 404


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


# ── New detail / file endpoints ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_project_detail_404_when_missing(admin_token: str) -> None:
    """GET /admin/projects/{id} returns 404 when the project does not exist."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/admin/projects/ghost-id", headers={"Authorization": f"Bearer {admin_token}"}
        )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_project_detail_returns_200(admin_token: str, override_get_db) -> None:
    """GET /admin/projects/{id} returns the project plus its image summaries."""
    proj = MagicMock(
        ProjectId="p1", UserId="u1", ProjectName="Default", Description=None, CreatedAt=None
    )
    img = MagicMock(ImageId="i1", ImagePath="x/i1.jpg", AnalysisStatus="completed", UploadedAt=None)
    bsr = MagicMock(FinalStyle="Gothic", Confidence=0.6)
    result = MagicMock()
    result.scalar_one_or_none.return_value = proj
    result.all.return_value = [(img, bsr)]
    override_get_db.execute.return_value = result

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/admin/projects/p1", headers={"Authorization": f"Bearer {admin_token}"}
        )
    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == "p1"
    assert body["total_images"] == 1
    assert body["images"][0]["style"] == "Gothic"


@pytest.mark.asyncio
async def test_image_detail_404_when_missing(admin_token: str) -> None:
    """GET /admin/images/{id} returns 404 when the image does not exist."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/admin/images/ghost-id", headers={"Authorization": f"Bearer {admin_token}"}
        )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_image_detail_returns_detail_json(admin_token: str, override_get_db) -> None:
    """GET /admin/images/{id} returns the stored DetailJson (admin, any owner)."""
    import json as _json

    img = MagicMock(ImageId="i1", ImagePath="D:\\up\\file-xyz.jpg")
    bsr = MagicMock(DetailJson=_json.dumps({"style": "Baroque", "confidence": 0.7}))
    result = MagicMock()
    result.first.return_value = (img, bsr)
    override_get_db.execute.return_value = result

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/admin/images/i1", headers={"Authorization": f"Bearer {admin_token}"}
        )
    assert response.status_code == 200
    body = response.json()
    assert body["style"] == "Baroque"
    assert body["image_id"] == "i1"
    assert body["file_id"] == "file-xyz"


@pytest.mark.asyncio
async def test_serve_file_404_when_missing(
    tmp_path: Path, admin_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GET /admin/files/{id}/raw returns 404 when no matching file exists."""
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/admin/files/missing-id/raw", headers={"Authorization": f"Bearer {admin_token}"}
        )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_file_returns_200(
    tmp_path: Path, admin_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DELETE /admin/files/{id} removes the on-disk file and reports deleted=True."""
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    (tmp_path / "abc.jpg").write_bytes(b"x")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.delete(
            "/admin/files/abc", headers={"Authorization": f"Bearer {admin_token}"}
        )
    assert response.status_code == 200
    body = response.json()
    assert body["file_id"] == "abc"
    assert body["deleted"] is True
    assert not (tmp_path / "abc.jpg").exists()


@pytest.mark.asyncio
async def test_delete_file_blocked_when_linked(
    tmp_path: Path, admin_token: str, override_get_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DELETE /admin/files/{id} returns 409 and keeps the file when it is linked."""
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    (tmp_path / "linked.jpg").write_bytes(b"x")
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = ["D:\\up\\linked.jpg"]  # an Image references file_id "linked"
    result.scalars.return_value = scalars
    override_get_db.execute.return_value = result

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.delete(
            "/admin/files/linked", headers={"Authorization": f"Bearer {admin_token}"}
        )
    assert response.status_code == 409
    assert (tmp_path / "linked.jpg").exists()  # not deleted


@pytest.mark.asyncio
async def test_delete_image_unlinks_physical_file(
    tmp_path: Path, admin_token: str, override_get_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DELETE /admin/images/{id} also removes the analysis's physical file."""
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    (tmp_path / "img1.jpg").write_bytes(b"x")
    result = MagicMock()
    result.scalar_one_or_none.return_value = str(tmp_path / "img1.jpg")
    result.rowcount = 1
    override_get_db.execute.return_value = result

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.delete(
            "/admin/images/i1", headers={"Authorization": f"Bearer {admin_token}"}
        )
    assert response.status_code == 200
    assert not (tmp_path / "img1.jpg").exists()  # file cleaned up


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

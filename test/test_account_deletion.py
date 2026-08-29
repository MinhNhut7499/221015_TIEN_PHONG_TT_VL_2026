"""Tests for user-initiated account + data deletion (DELETE /auth/account).

HTTP tests use the autouse ``override_get_db`` mock from conftest. Unit tests
call the service/router helpers directly with an AsyncSession mock so they can
verify the deletion sequence (CAS lock, per-project delete, anti-resurrection
guard) that the shared mock cannot express.

Honest scope: these verify call orchestration, NOT real FK cascade or physical
file removal — those need the DB smoke test described in the plan.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.security.security import create_access_token


@pytest.fixture
def user_token() -> str:
    """Valid JWT for a regular user."""
    return create_access_token({"sub": "user-uid-001", "email": "user@test.com", "role": "user"})


# ── HTTP-level ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_account_no_token_returns_403() -> None:
    """DELETE /auth/account without a token is rejected by the bearer scheme."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.delete("/auth/account")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_delete_account_happy_path_returns_200(user_token: str) -> None:
    """Active account → 200 with deleted=True (default mock: rowcount=1, no projects)."""
    headers = {"Authorization": f"Bearer {user_token}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.delete("/auth/account", headers=headers)
    assert response.status_code == 200
    assert response.json()["deleted"] is True


@pytest.mark.asyncio
async def test_delete_account_deactivated_returns_403(user_token: str, override_get_db) -> None:
    """A deactivated/already-deleted account is blocked by get_current_active_user."""
    blocked = MagicMock()
    blocked.scalar_one_or_none.return_value = False
    override_get_db.execute.return_value = blocked

    headers = {"Authorization": f"Bearer {user_token}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.delete("/auth/account", headers=headers)
    assert response.status_code == 403


# ── Service unit tests ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_own_account_anonymises_and_deletes(monkeypatch) -> None:
    """CAS rowcount>0 → content removed, account anonymised, deleted=True."""
    from app.services import account_service

    db = AsyncMock(spec=AsyncSession)
    cas = MagicMock()
    cas.rowcount = 1
    db.execute.return_value = cas

    async def fake_delete_user_projects(_db, _uid):
        return 3

    monkeypatch.setattr(
        account_service.project_service, "delete_user_projects", fake_delete_user_projects
    )

    result = await account_service.delete_own_account(db, "user-uid-001")
    assert result.deleted is True
    assert result.projects_deleted == 3
    db.commit.assert_awaited()  # CAS update was committed


@pytest.mark.asyncio
async def test_delete_own_account_idempotent_when_already_deleted(monkeypatch) -> None:
    """CAS rowcount=0 (concurrent/repeat) → deleted=False, content step skipped."""
    from app.services import account_service

    db = AsyncMock(spec=AsyncSession)
    cas = MagicMock()
    cas.rowcount = 0
    db.execute.return_value = cas

    called = False

    async def fake_delete_user_projects(_db, _uid):
        nonlocal called
        called = True
        return 0

    monkeypatch.setattr(
        account_service.project_service, "delete_user_projects", fake_delete_user_projects
    )

    result = await account_service.delete_own_account(db, "user-uid-001")
    assert result.deleted is False
    assert called is False  # no content deletion when the account was already gone


@pytest.mark.asyncio
async def test_delete_user_projects_calls_delete_per_project(monkeypatch) -> None:
    """delete_user_projects fans out to delete_project once per owned project id."""
    from app.services import project_service

    db = AsyncMock(spec=AsyncSession)
    ids_result = MagicMock()
    ids_result.scalars.return_value.all.return_value = ["p1", "p2", "p3"]
    db.execute.return_value = ids_result

    calls = []

    async def fake_delete_project(_db, pid):
        calls.append(pid)
        return True

    monkeypatch.setattr(project_service, "delete_project", fake_delete_project)

    removed = await project_service.delete_user_projects(db, "user-uid-001")
    assert removed == 3
    assert calls == ["p1", "p2", "p3"]


@pytest.mark.asyncio
async def test_persist_result_skips_when_account_inactive() -> None:
    """Anti-resurrection: a finishing pipeline must not re-create rows for a
    self-deleted (anonymised, IsActive=False) account."""
    from app.routers.analyze import _persist_result

    db = AsyncMock(spec=AsyncSession)
    lookup = MagicMock()
    lookup.scalar_one_or_none.return_value = False  # account anonymised
    db.execute.return_value = lookup

    out = await _persist_result(db, "user-uid-001", "file.jpg", MagicMock())
    assert out is None
    assert db.execute.await_count == 1  # only the IsActive lookup ran; nothing persisted

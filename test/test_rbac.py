"""Tests for the lightweight RBAC permission layer.

Run with: pytest test/ -v
"""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.security import permissions
from app.security.security import create_access_token


def test_admin_is_superset_of_user() -> None:
    """Admin holds every user permission plus the admin-only ones."""
    assert permissions.ROLE_PERMISSIONS["user"].issubset(permissions.ROLE_PERMISSIONS["admin"])
    assert permissions.role_has_permission("admin", permissions.PERM_ANALYZE)
    assert permissions.role_has_permission("admin", permissions.PERM_APIKEYS_MANAGE)
    assert permissions.role_has_permission("admin", permissions.PERM_CMS_MANAGE)


def test_user_lacks_admin_permissions() -> None:
    """A plain user can analyze but cannot manage keys or content."""
    assert permissions.role_has_permission("user", permissions.PERM_ANALYZE)
    assert not permissions.role_has_permission("user", permissions.PERM_APIKEYS_MANAGE)
    assert not permissions.role_has_permission("user", permissions.PERM_CMS_MANAGE)


def test_unknown_role_has_no_permissions() -> None:
    """An unrecognised role grants nothing."""
    assert not permissions.role_has_permission("ghost", permissions.PERM_ANALYZE)


@pytest.mark.asyncio
async def test_cms_publish_user_forbidden_admin_allowed() -> None:
    """require_permission gates the CMS publish endpoint by role."""
    user_token = create_access_token({"sub": "u", "email": "u@t.com", "role": "user"})
    admin_token = create_access_token({"sub": "a", "email": "a@t.com", "role": "admin"})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user_res = await client.get(
            "/admin/cms/landing/revisions",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        admin_res = await client.get(
            "/admin/cms/landing/revisions",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert user_res.status_code == 403
    assert admin_res.status_code == 200


@pytest.mark.asyncio
async def test_admin_email_bootstrap_grants_permission(monkeypatch) -> None:
    """A token without a role claim but on the ADMIN_EMAILS list is treated as admin."""
    from app.config import settings

    monkeypatch.setattr(
        type(settings), "admin_emails_list",
        property(lambda self: ["boot@test.com"]),
    )
    token = create_access_token({"sub": "b", "email": "boot@test.com"})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(
            "/admin/api-keys", headers={"Authorization": f"Bearer {token}"}
        )
    assert res.status_code == 200

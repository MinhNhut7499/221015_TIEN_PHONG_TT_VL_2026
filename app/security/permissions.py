"""Role-based access control (RBAC) permission map.

A deliberately lightweight, code-defined RBAC: the database stores the role
NAME ('user' | 'admin') and this module maps a role to the set of permissions
it grants. This is enough for the two roles in use and avoids a full
permissions table; ``ROLE_PERMISSIONS`` is the single seam to extend later
(add a role, add a permission, or back it with a DB table) without touching the
``require_permission`` call sites.

Admin is a SUPERSET of user — admins hold every user permission plus the admin
ones — which encodes the "admin is a special user" rule.
"""
from __future__ import annotations

from typing import Dict, Set

# Permission identifiers (resource:action style, '*' = wildcard).
PERM_ANALYZE = "analyze"
PERM_UPLOAD = "upload"
PERM_BILLING = "billing"
PERM_APIKEYS_MANAGE = "apikeys:manage"
PERM_CMS_MANAGE = "cms:manage"
PERM_ADMIN = "admin:*"

_USER_PERMS: Set[str] = {PERM_ANALYZE, PERM_UPLOAD, PERM_BILLING}
_ADMIN_PERMS: Set[str] = _USER_PERMS | {
    PERM_APIKEYS_MANAGE,
    PERM_CMS_MANAGE,
    PERM_ADMIN,
}

ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    "user": _USER_PERMS,
    "admin": _ADMIN_PERMS,
}


def role_has_permission(role: str, permission: str) -> bool:
    """Return True if *role* grants *permission* (admin wildcard counts)."""
    granted = ROLE_PERMISSIONS.get((role or "").lower(), set())
    return permission in granted or PERM_ADMIN in granted

"""Smoke test the hybrid-login session lifecycle against the REAL database.

No Google, no Flutter app: drives the service layer directly, each step in its
own DB session (like separate HTTP requests), and verifies the full flow:
register -> pending -> complete -> completed(+token once) -> expired -> guard.

Usage:
    python scripts/smoke_login_session.py
"""
import asyncio
import sys
import uuid
from pathlib import Path

# Make the project root importable when run as ``python scripts/...``.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.database import AsyncSessionLocal, engine  # noqa: E402
from app.services import login_session_service as svc  # noqa: E402


async def main() -> None:
    sid = str(uuid.uuid4())
    print("session_id =", sid, "\n")

    # 1) Web registers the pending session (POST /auth/login-session).
    async with AsyncSessionLocal() as db:
        await svc.create_session(db, sid)
        await db.commit()
    print("[1] create_session       -> pending row created")

    # 2) Web polls (GET .../{id}) -> pending.
    async with AsyncSessionLocal() as db:
        r = await svc.poll_session(db, sid)
        await db.commit()
    print("[2] poll #1              ->", r)
    assert r["status"] == "pending"

    # 3) Simulate the flutter callback completing login (stores the JWT pair).
    async with AsyncSessionLocal() as db:
        ok = await svc.complete_session(db, sid, "FAKE_ACCESS", "FAKE_REFRESH", "fake-user-id")
        await db.commit()
    print("[3] complete_session     ->", ok)
    assert ok is True

    # 4) Web polls -> completed + tokens (claimed exactly once).
    async with AsyncSessionLocal() as db:
        r = await svc.poll_session(db, sid)
        await db.commit()
    print("[4] poll #2              ->", r)
    assert r["status"] == "completed" and r["access_token"] == "FAKE_ACCESS"

    # 5) Web polls again -> expired (one-time use proven: the row is gone).
    async with AsyncSessionLocal() as db:
        r = await svc.poll_session(db, sid)
        await db.commit()
    print("[5] poll #3              ->", r)
    assert r["status"] == "expired"

    # 6) complete on an unknown session -> False (no row is created/overwritten).
    async with AsyncSessionLocal() as db:
        ok = await svc.complete_session(db, str(uuid.uuid4()), "x", "y", "z")
        await db.commit()
    print("[6] complete unknown     ->", ok)
    assert ok is False

    await engine.dispose()
    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())

"""Simulate the Flutter app finishing Google login, for testing WITHOUT the app.

Marks an existing pending login session as completed with placeholder tokens —
exactly what GET /auth/google/callback/flutter does after a real Google login,
but without needing Google credentials. Use it to test the polling endpoints
end-to-end over HTTP.

Usage:
    python scripts/simulate_app_login.py <session_id>
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
from app.security.security import create_access_token, create_refresh_token  # noqa: E402
from app.services import login_session_service as svc  # noqa: E402


async def main(session_id: str) -> None:
    payload = {
        "sub": "sim-" + uuid.uuid4().hex[:8],
        "email": "sim@test.com",
        "name": "Simulated User",
        "role": "user",
    }
    async with AsyncSessionLocal() as db:
        ok = await svc.complete_session(
            db,
            session_id,
            access_token=create_access_token(payload),
            refresh_token=create_refresh_token(payload),
            user_id=payload["sub"],
        )
        await db.commit()
    await engine.dispose()
    if ok:
        print(f"OK: session {session_id} marked completed (tokens stored).")
    else:
        print(f"FAILED: session {session_id} is missing, expired, or already completed.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/simulate_app_login.py <session_id>")
        raise SystemExit(1)
    asyncio.run(main(sys.argv[1]))

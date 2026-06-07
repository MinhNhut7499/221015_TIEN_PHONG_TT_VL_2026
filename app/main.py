"""FastAPI application factory and entry point.

Import `app` from this module to run with uvicorn:
    uvicorn app.main:app --reload
"""
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import check_db_connection, engine
from app.routers import admin, analyze, auth, base, file_upload

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_application: FastAPI) -> AsyncGenerator[None, None]:
    """Manage startup and graceful shutdown of shared resources.

    On startup: verifies the database is reachable (non-fatal warning on failure).
    On shutdown: disposes the connection pool so all idle connections are closed.
    """
    db_ok = await check_db_connection()
    if db_ok:
        from app.database import ensure_roles_seeded
        try:
            await ensure_roles_seeded()
        except Exception as exc:
            logger.warning("Role seeding skipped — table not ready. Reason: %s", exc)
    yield
    await engine.dispose()
    logger.info("Database connection pool disposed.")


def create_application() -> FastAPI:
    """Construct and configure the FastAPI application instance.

    Registers middleware, mounts all API routers, and returns
    a fully configured application ready to be served.
    """
    application = FastAPI(
        title=settings.APP_NAME,
        description=(
            "Backend API for the Architecture AI system. "
            "Handles authentication, image upload, and AI analysis results."
        ),
        version=settings.APP_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # ── Middleware ─────────────────────────────────────────────────────────────
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ────────────────────────────────────────────────────────────────
    application.include_router(base.router, tags=["Health"])
    application.include_router(auth.router, prefix="/auth", tags=["Authentication"])
    application.include_router(file_upload.router, prefix="/upload", tags=["File Upload"])
    application.include_router(admin.router, prefix="/admin", tags=["Admin"])
    application.include_router(analyze.router, prefix="/analyze", tags=["Analysis"])

    return application


app: FastAPI = create_application()

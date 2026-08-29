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
from app.routers import (
    admin,
    admin_api_keys,
    admin_billing,
    admin_cms,
    analyze,
    auth,
    base,
    billing,
    content,
    file_upload,
    kb_admin,
    knowledge,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_application: FastAPI) -> AsyncGenerator[None, None]:
    """Manage startup and graceful shutdown of shared resources.

    On startup: verifies the database is reachable (non-fatal warning on failure).
    On shutdown: disposes the connection pool so all idle connections are closed.
    """
    db_ok = await check_db_connection()
    if db_ok:
        from app.database import (
            ensure_agents_seeded,
            ensure_plans_seeded,
            ensure_roles_seeded,
        )
        try:
            await ensure_roles_seeded()
        except Exception as exc:
            logger.warning("Role seeding skipped — table not ready. Reason: %s", exc)
        try:
            await ensure_agents_seeded()
        except Exception as exc:
            logger.warning("Agent seeding skipped — table not ready. Reason: %s", exc)
        try:
            await ensure_plans_seeded()
        except Exception as exc:
            logger.warning("Plan seeding skipped — table not ready. Reason: %s", exc)
        # Warm the provider-key snapshot so the first request sees DB-managed keys
        # immediately (best-effort; falls back to .env if the table is absent).
        try:
            from app.database import AsyncSessionLocal
            from chatbot.services import provider_credentials

            async with AsyncSessionLocal() as session:
                await provider_credentials.refresh_snapshot(session)
        except Exception as exc:
            logger.warning("Provider key snapshot warm-up skipped: %s", exc)
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
        # API documentation pages are disabled — do not expose the API surface
        # (Swagger UI, ReDoc, and the OpenAPI schema) publicly.
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
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
    application.include_router(knowledge.router, prefix="/knowledge", tags=["Knowledge"])
    application.include_router(kb_admin.router, prefix="/admin/kb", tags=["Admin KB"])
    application.include_router(billing.router, prefix="/billing", tags=["Billing"])
    application.include_router(admin_billing.router, prefix="/admin", tags=["Admin Billing"])
    application.include_router(admin_api_keys.router, prefix="/admin", tags=["Admin API Keys"])
    application.include_router(admin_cms.router, prefix="/admin", tags=["Admin CMS"])
    application.include_router(content.router, prefix="/content", tags=["Content"])

    return application


app: FastAPI = create_application()

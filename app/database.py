"""Async database engine and session management.

Provides:
- ``engine``             — singleton AsyncEngine with QueuePool
- ``AsyncSessionLocal``  — session factory (expire_on_commit=False)
- ``get_db``             — FastAPI dependency yielding an AsyncSession
- ``check_db_connection`` — startup health-check helper
- ``Base``               — DeclarativeBase for ORM table classes
"""
import logging
from collections.abc import AsyncGenerator

from sqlalchemy import select, text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import AsyncAdaptedQueuePool

from app.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Declarative base for all SQLAlchemy ORM table models."""


def _build_url() -> URL:
    """Construct the SQLAlchemy async connection URL from settings.

    Uses ``URL.create`` so that special characters in credentials
    are percent-encoded automatically.
    """
    return URL.create(
        drivername="mssql+aioodbc",
        username=settings.DB_USER,
        password=settings.DB_PASSWORD,
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        database=settings.DB_NAME,
        query={
            "driver": settings.DB_ODBC_DRIVER,
            "Encrypt": "yes" if settings.DB_ENCRYPT else "no",
            "TrustServerCertificate": "yes" if settings.DB_TRUST_SERVER_CERT else "no",
        },
    )


def _build_engine() -> AsyncEngine:
    """Create the async engine with connection-pool configuration.

    ``pool_pre_ping=True`` causes SQLAlchemy to emit a lightweight
    ``SELECT 1`` before handing a connection from the pool, evicting
    stale connections automatically after a network drop or server restart.
    """
    return create_async_engine(
        _build_url(),
        poolclass=AsyncAdaptedQueuePool,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
        pool_recycle=settings.DB_POOL_RECYCLE,
        pool_pre_ping=True,
        echo=settings.DEBUG,
    )


engine: AsyncEngine = _build_engine()

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a database session.

    Commits automatically on a clean exit; rolls back on any exception
    and re-raises so the router can return an appropriate HTTP error.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def ensure_roles_seeded() -> None:
    """Insert the default 'user' and 'admin' roles if they do not yet exist.

    Idempotent: safe to call on every startup. Performs a single SELECT,
    then INSERTs only the missing role names.
    """
    from app.models.orm_models import Role  # local import avoids circular dependency

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Role))
        existing = {row.RoleName for row in result.scalars().all()}
        for name in ("user", "admin"):
            if name not in existing:
                session.add(Role(RoleName=name))
        await session.commit()


async def check_db_connection() -> bool:
    """Emit a lightweight ping to verify the database is reachable.

    Returns True on success. Logs a warning and returns False if the
    database is unreachable so the application can start in offline mode.
    """
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connection verified (host=%s db=%s).", settings.DB_HOST, settings.DB_NAME)
        return True
    except Exception as exc:
        logger.warning("Database ping failed — running in offline mode. Reason: %s", exc)
        return False

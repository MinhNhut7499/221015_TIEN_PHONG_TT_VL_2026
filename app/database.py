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


async def ensure_agents_seeded() -> None:
    """Insert the open-vocabulary pipeline agents and prune legacy ones.

    Idempotent: matches on ``AgentName`` and only inserts the missing rows.
    Agent names must match the telemetry labels emitted by the pipeline
    (``Agent A``, ``Panel: …``, ``Arbiter``) so AgentRuns can be attributed.

    Descriptions are ASCII-only on purpose: ``Agents.Description`` is a non-
    Unicode SQL Server column, so Vietnamese diacritics would be stored as
    ``?``. The admin UI renders rich Vietnamese labels from a frontend map keyed
    by the (ASCII-safe) agent name instead.

    Legacy ``Agent 1`` … ``Agent 7`` rows from the retired closed-set pipeline
    are deleted so the admin roster shows only the 5 agents actually in use.
    """
    from app.models.orm_models import Agent  # local import avoids circular dependency
    from chatbot.services import provider_credentials

    g = provider_credentials.get_credentials("gemini").model
    o = provider_credentials.get_credentials("openai").model
    gr = provider_credentials.get_credentials("xai").model
    seed = {
        "Agent A": f"12-dimension evidence extraction from image (vision) - Gemini {g}",
        "Panel: Gemini": f"Independent style-mixture judge (vision) - Gemini {g}",
        "Panel: OpenAI": f"Independent style-mixture judge (vision) - OpenAI {o}",
        "Panel: Grok": f"Independent style-mixture judge (vision) - Grok {gr}",
        "Arbiter": f"Final arbiter, reconciles 3 verdicts + image via CoT - OpenAI {o}",
    }
    # Legacy closed-set agents + the retired DeepSeek judge (DeepSeek now only
    # translates, emitting no AgentRuns) are pruned so the roster shows the five
    # agents actually attributed in telemetry.
    legacy_names = [f"Agent {i}" for i in range(1, 8)] + ["Panel: DeepSeek"]

    # Seed the 5 active agents first and commit on its own, so legacy cleanup
    # (which may be blocked by AgentRuns FK references) can never prevent it.
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Agent))
        existing = {row.AgentName for row in result.scalars().all()}
        for name, description in seed.items():
            if name not in existing:
                session.add(Agent(AgentName=name, Description=description))
        await session.commit()

    # Best-effort: prune legacy closed-set agents in a separate transaction.
    # If AgentRuns still reference them the delete fails — that is fine, the
    # admin UI hides any agent not in the active set regardless.
    async with AsyncSessionLocal() as session:
        try:
            legacy = await session.execute(
                select(Agent).where(Agent.AgentName.in_(legacy_names))
            )
            rows = legacy.scalars().all()
            for row in rows:
                await session.delete(row)
            await session.commit()
        except Exception as exc:
            logger.warning("Could not prune legacy agents (referenced by AgentRuns?): %s", exc)
            await session.rollback()


async def ensure_plans_seeded() -> None:
    """Insert the default billing plans if they do not yet exist.

    Idempotent: matches on ``PlanCode`` and only inserts the missing rows, so an
    admin's later price/token edits are never overwritten. Tier benefits (e.g. a
    lower per-analysis cost) live in ``BenefitsJson``.
    """
    import json
    from datetime import datetime, timezone

    from app.models.orm_models import Plan  # local import avoids circular dependency

    now = datetime.now(timezone.utc)
    # (code, name, type, price_vnd, tokens, duration_days, benefits, sort)
    catalog = [
        ("free", "Free", "subscription", 0, 0, None, None, 0),
        ("pro", "Pro", "subscription", 99_000, 500, 30, {"cost_per_analysis": 2}, 10),
        ("premium", "Premium", "subscription", 199_000, 1500, 30,
         {"cost_per_analysis": 1}, 20),
        ("pack_100", "100 Tokens", "token_pack", 20_000, 100, None, None, 100),
        ("pack_500", "500 Tokens", "token_pack", 90_000, 500, None, None, 110),
        ("pack_1000", "1000 Tokens", "token_pack", 160_000, 1000, None, None, 120),
    ]

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Plan.PlanCode))
        existing = {row[0] for row in result.all()}
        for code, name, ptype, price, tokens, duration, benefits, order in catalog:
            if code in existing:
                continue
            session.add(
                Plan(
                    PlanCode=code,
                    PlanName=name,
                    PlanType=ptype,
                    PriceAmount=price,
                    Currency="VND",
                    TokenAmount=tokens,
                    DurationDays=duration,
                    BenefitsJson=json.dumps(benefits) if benefits else None,
                    SortOrder=order,
                    IsActive=True,
                    CreatedAt=now,
                )
            )
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

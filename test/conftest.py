"""Shared pytest fixtures for the test suite.

Provides an autouse fixture that overrides ``get_db`` with an in-memory
AsyncSession mock. Every ``execute`` call returns an "empty result" by
default, so DB-backed endpoints behave as if the database is empty.
``rowcount`` is 1 so UPDATE/DELETE operations report success in happy-path
tests without needing real rows.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.main import app
from chatbot.utils.circuit_breaker import get_circuit_breaker


@pytest.fixture(autouse=True)
def reset_circuit_breaker():
    """Clear the shared provider circuit breaker before each test.

    The breaker is a process-wide singleton; failures injected by one test must
    not leak into the next (e.g. opening a provider's circuit), so reset it.
    """
    get_circuit_breaker().reset()
    yield


def _make_empty_result() -> MagicMock:
    """Return a mock SQLAlchemy Result that mimics an empty query response."""
    result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = []
    scalars_mock.first.return_value = None
    result.scalars.return_value = scalars_mock
    result.all.return_value = []
    result.scalar_one_or_none.return_value = None
    result.scalar_one.return_value = None
    result.first.return_value = None
    result.rowcount = 1
    return result


@pytest.fixture(autouse=True)
def override_get_db():
    """Replace the real ``get_db`` dependency with an in-memory AsyncSession mock.

    The fixture yields the mock session so individual tests can override
    specific call results (e.g. ``mock_session.execute.return_value = ...``).
    """
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.execute.return_value = _make_empty_result()
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.add = MagicMock()

    async def _mock_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = _mock_get_db
    yield mock_session
    app.dependency_overrides.pop(get_db, None)

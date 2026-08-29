"""Tests for the grounded follow-up Q&A endpoint (POST /analyze/{id}/ask).

The LLM is mocked: ``get_qa_service`` is patched to return a fake whose
``answer`` echoes a canned string, so the test exercises auth, ownership, and
the 503 guard without any network call.
"""
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

import app.routers.analyze as analyze_router
from app.config import settings
from app.main import app
from app.security.security import create_access_token


@pytest.fixture
def user_token() -> str:
    """Valid JWT for a regular user."""
    return create_access_token({"sub": "user-uid-001", "email": "user@test.com", "role": "user"})


def _row():
    """Mock result whose .first() returns (Image, BuildingStyleResult) with DetailJson."""
    img = MagicMock()
    img.ImagePath = "D:\\uploads\\file-abc.jpg"
    bsr = MagicMock()
    bsr.FinalStyle = "Gothic"
    bsr.Confidence = 0.62
    bsr.Explanation = "Predominantly Gothic."
    bsr.KeyEvidence = "pointed arch\nspire"
    bsr.DetailJson = json.dumps({"style": "Gothic", "confidence": 0.62, "candidate_names": ["Gothic"]})
    result = MagicMock()
    result.first.return_value = (img, bsr)
    return result


@pytest.mark.asyncio
async def test_ask_returns_answer(user_token: str, override_get_db, monkeypatch) -> None:
    """Owned analysis + configured LLM → returns the assistant's answer."""
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "test-key")
    override_get_db.execute.return_value = _row()

    fake = MagicMock()
    fake.answer = AsyncMock(return_value="Because the evidence shows pointed arches.")
    monkeypatch.setattr(analyze_router, "get_qa_service", lambda: fake)

    headers = {"Authorization": f"Bearer {user_token}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/analyze/img-1/ask",
            headers=headers,
            json={"question": "Why not Romanesque?", "history": [], "lang": "en"},
        )

    assert response.status_code == 200
    assert response.json()["answer"].startswith("Because")
    fake.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_ask_not_owned_returns_404(user_token: str, monkeypatch) -> None:
    """Configured LLM but image not owned (empty DB) → 404."""
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "test-key")
    headers = {"Authorization": f"Bearer {user_token}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/analyze/nope/ask",
            headers=headers,
            json={"question": "Why?", "history": [], "lang": "en"},
        )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_ask_503_when_llm_not_configured(user_token: str, monkeypatch) -> None:
    """No DEEPSEEK_API_KEY → 503 before any DB / LLM work."""
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "")
    headers = {"Authorization": f"Bearer {user_token}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/analyze/img-1/ask",
            headers=headers,
            json={"question": "Why?", "history": [], "lang": "en"},
        )
    assert response.status_code == 503

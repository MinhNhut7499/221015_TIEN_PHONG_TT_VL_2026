"""Tests for re-accessing past analyses.

Covers the two endpoints added so users can re-open a previous analysis:
- GET /analyze/history/{image_id}  → full DetailJson, or summary fallback, 404 if not owned
- GET /analyze/image/{image_id}    → 404 when not owned / file missing

Uses the autouse ``override_get_db`` fixture from conftest; tests that need a
matching row override ``execute`` to return a fake (Image, BuildingStyleResult).
"""
import json
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.security.security import create_access_token


@pytest.fixture
def user_token() -> str:
    """Valid JWT for a regular user."""
    return create_access_token({"sub": "user-uid-001", "email": "user@test.com", "role": "user"})


def _row(detail_json):
    """Build a mock SQLAlchemy result whose .first() returns (Image, BuildingStyleResult)."""
    img = MagicMock()
    img.ImagePath = "D:\\uploads\\file-abc.jpg"
    bsr = MagicMock()
    bsr.FinalStyle = "Gothic"
    bsr.Confidence = 0.62
    bsr.Explanation = "Predominantly Gothic."
    bsr.KeyEvidence = "pointed arch\nspire"
    bsr.DetailJson = detail_json
    result = MagicMock()
    result.first.return_value = (img, bsr)
    return result


@pytest.mark.asyncio
async def test_detail_not_owned_returns_404(user_token: str) -> None:
    """Default empty DB → no matching owned image → 404."""
    headers = {"Authorization": f"Bearer {user_token}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/analyze/history/some-image-id", headers=headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_detail_returns_full_from_detail_json(user_token: str, override_get_db) -> None:
    """When DetailJson is present, the full stored AnalyzeResponse is returned."""
    detail = {
        "style": "Gothic",
        "confidence": 0.62,
        "explanation": "Predominantly Gothic with Renaissance influence.",
        "key_evidence": ["pointed arch", "spire"],
        "components": [],
        "processing_time_ms": 41000.0,
        "style_distribution": {
            "distribution": {"Gothic": 0.6, "Renaissance": 0.4},
            "primary": "Gothic",
            "secondary": ["Renaissance"],
        },
    }
    override_get_db.execute.return_value = _row(json.dumps(detail))

    headers = {"Authorization": f"Bearer {user_token}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/analyze/history/img-1", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["style"] == "Gothic"
    assert body["style_distribution"]["primary"] == "Gothic"
    assert body["image_id"] == "img-1"
    assert body["file_id"] == "file-abc"


@pytest.mark.asyncio
async def test_detail_summary_fallback_when_no_detail_json(user_token: str, override_get_db) -> None:
    """When DetailJson is NULL, a summary is built from the persisted fields."""
    override_get_db.execute.return_value = _row(None)

    headers = {"Authorization": f"Bearer {user_token}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/analyze/history/img-2", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["style"] == "Gothic"
    assert body["confidence"] == 0.62
    assert body["key_evidence"] == ["pointed arch", "spire"]
    assert body["components"] == []


@pytest.mark.asyncio
async def test_deactivated_user_is_blocked_403(user_token: str, override_get_db) -> None:
    """An authenticated user whose IsActive is False is rejected with 403.

    The first DB call in the request is get_current_active_user's IsActive
    lookup; returning False short-circuits before the handler runs.
    """
    blocked = MagicMock()
    blocked.scalar_one_or_none.return_value = False
    override_get_db.execute.return_value = blocked

    headers = {"Authorization": f"Bearer {user_token}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/analyze/history/any-id", headers=headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_image_not_owned_returns_404(user_token: str) -> None:
    """Default empty DB → image not owned → 404."""
    headers = {"Authorization": f"Bearer {user_token}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/analyze/image/some-image-id", headers=headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_image_owned_but_file_missing_returns_404(user_token: str, override_get_db) -> None:
    """Owned image whose file is absent on disk → 404 from _find_upload_path."""
    override_get_db.execute.return_value = _row(None)  # ImagePath stem 'file-abc' has no file

    headers = {"Authorization": f"Bearer {user_token}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/analyze/image/img-3", headers=headers)
    assert response.status_code == 404

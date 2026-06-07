"""Smoke tests for the base/health-check endpoints.

Run with:
    pytest test/ -v

Requires:
    pip install pytest pytest-asyncio httpx
"""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_root_returns_ok() -> None:
    """GET / should return HTTP 200 with status='ok'."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "app_name" in body


@pytest.mark.asyncio
async def test_health_check_returns_ok() -> None:
    """GET /health should return HTTP 200 with status='ok'."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"


@pytest.mark.asyncio
async def test_upload_without_token_returns_403() -> None:
    """POST /upload/image without a Bearer token should return HTTP 403."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/upload/image", files={"file": ("test.jpg", b"fake", "image/jpeg")})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_openapi_schema_is_accessible() -> None:
    """GET /openapi.json should return a valid OpenAPI schema."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "openapi" in schema
    assert "paths" in schema

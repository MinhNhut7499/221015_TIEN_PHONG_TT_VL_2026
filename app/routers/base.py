"""Base router.

Provides the health-check and root endpoints used by load balancers,
monitoring agents, and developers to verify the API is running.
"""
from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings

router = APIRouter()


class HealthResponse(BaseModel):
    """Structured response for health-check endpoints."""

    status: str
    app_name: str
    environment: str
    version: str


@router.get(
    "/",
    response_model=HealthResponse,
    summary="Root endpoint",
    description="Returns basic API identification. Useful for quick connectivity tests.",
)
async def root() -> HealthResponse:
    """Return the application name, environment, and version."""
    return HealthResponse(
        status="ok",
        app_name=settings.APP_NAME,
        environment=settings.APP_ENV,
        version=settings.APP_VERSION,
    )


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Deep health check endpoint polled by load balancers and CI pipelines.",
)
async def health_check() -> HealthResponse:
    """Return service health status.

    Extend this endpoint in the future to check DB connectivity,
    LLM service reachability, and disk space on the upload directory.
    """
    return HealthResponse(
        status="ok",
        app_name=settings.APP_NAME,
        environment=settings.APP_ENV,
        version=settings.APP_VERSION,
    )

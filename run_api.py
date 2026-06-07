"""Entry point for running the API server with uvicorn.

Usage (from the api_base/ directory):
    python run_api.py

For production, use a process manager (systemd, supervisord, gunicorn+uvicorn workers)
instead of running this script directly.
"""
import sys
from pathlib import Path

# Ensure api_base/ is on the Python path so `app` package is importable
# when running this script directly rather than via `python -m`.
sys.path.insert(0, str(Path(__file__).parent))

import uvicorn

from app.config import settings


def main() -> None:
    """Start the uvicorn server with settings loaded from .env."""
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="debug" if settings.DEBUG else "info",
        workers=1,  # increase for production; must disable reload first
    )


if __name__ == "__main__":
    main()

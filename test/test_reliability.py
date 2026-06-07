"""Unit tests for the transient-error retry helper (chatbot/utils/llm_retry.py)."""
import asyncio

import pytest

from chatbot.utils.llm_retry import is_transient, with_retry


class _StatusError(Exception):
    """Exception exposing a numeric status_code, like the OpenAI SDK."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"http {status_code}")
        self.status_code = status_code


# ── is_transient ───────────────────────────────────────────────────────────────

def test_is_transient_detects_overloaded_message() -> None:
    assert is_transient(RuntimeError("503 The model is overloaded")) is True


def test_is_transient_detects_timeout() -> None:
    assert is_transient(asyncio.TimeoutError()) is True


def test_is_transient_detects_status_code_attribute() -> None:
    assert is_transient(_StatusError(429)) is True
    assert is_transient(_StatusError(503)) is True


def test_is_transient_rejects_client_errors() -> None:
    assert is_transient(ValueError("bad input")) is False
    assert is_transient(RuntimeError("invalid api key")) is False
    assert is_transient(_StatusError(400)) is False


# ── with_retry ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_with_retry_succeeds_after_transient_failures() -> None:
    calls = {"n": 0}

    async def factory() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("503 overloaded")
        return "ok"

    result = await with_retry(factory, attempts=3, base_delay=0.0)
    assert result == "ok"
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_with_retry_does_not_retry_non_transient() -> None:
    calls = {"n": 0}

    async def factory() -> str:
        calls["n"] += 1
        raise ValueError("bad request")

    with pytest.raises(ValueError):
        await with_retry(factory, attempts=3, base_delay=0.0)
    assert calls["n"] == 1  # raised immediately, no retry


@pytest.mark.asyncio
async def test_with_retry_exhausts_attempts() -> None:
    calls = {"n": 0}

    async def factory() -> str:
        calls["n"] += 1
        raise RuntimeError("429 rate limit")

    with pytest.raises(RuntimeError):
        await with_retry(factory, attempts=2, base_delay=0.0)
    assert calls["n"] == 2

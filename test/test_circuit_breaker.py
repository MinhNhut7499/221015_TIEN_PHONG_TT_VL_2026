"""Tests for the provider circuit breaker + fallback runner (A4b).

Covers: opening after the failure threshold, fast-skip while open, closing on a
success, and ``call_with_fallback`` trying providers in order (skipping open
circuits) until one succeeds.
"""
import pytest

from chatbot.utils.circuit_breaker import CircuitBreaker, call_with_fallback


def test_breaker_opens_after_threshold() -> None:
    """Three consecutive failures open the circuit (threshold = 3)."""
    cb = CircuitBreaker(fail_threshold=3, cooldown_sec=60.0)
    assert cb.is_open("gemini") is False
    cb.record_failure("gemini")
    cb.record_failure("gemini")
    assert cb.is_open("gemini") is False  # 2 < 3
    cb.record_failure("gemini")
    assert cb.is_open("gemini") is True   # 3 → open


def test_breaker_success_resets() -> None:
    """A success closes the circuit and clears the failure count."""
    cb = CircuitBreaker(fail_threshold=2, cooldown_sec=60.0)
    cb.record_failure("openai")
    cb.record_failure("openai")
    assert cb.is_open("openai") is True
    cb.record_success("openai")
    assert cb.is_open("openai") is False


def test_breaker_cooldown_expires() -> None:
    """Once the cooldown elapses the circuit is no longer open."""
    cb = CircuitBreaker(fail_threshold=1, cooldown_sec=0.0)
    cb.record_failure("grok")
    # cooldown 0 → open_until is now; is_open uses strict `<`, so it reads closed.
    assert cb.is_open("grok") is False


@pytest.mark.asyncio
async def test_call_with_fallback_uses_first_success() -> None:
    """The first working provider answers; later ones are not called."""
    calls: list[str] = []

    async def ok() -> str:
        calls.append("a")
        return "A"

    async def never() -> str:  # pragma: no cover - must not run
        calls.append("b")
        return "B"

    cb = CircuitBreaker()
    out = await call_with_fallback([("a", ok), ("b", never)], breaker=cb)
    assert out == "A"
    assert calls == ["a"]


@pytest.mark.asyncio
async def test_call_with_fallback_skips_failing_provider() -> None:
    """A failing primary falls through to the working fallback."""
    async def boom() -> str:
        raise RuntimeError("down")

    async def ok() -> str:
        return "B"

    cb = CircuitBreaker()
    out = await call_with_fallback([("a", boom), ("b", ok)], breaker=cb)
    assert out == "B"


@pytest.mark.asyncio
async def test_call_with_fallback_tries_open_circuit_as_last_resort() -> None:
    """If every circuit is open, the chain is still attempted once."""
    cb = CircuitBreaker(fail_threshold=1, cooldown_sec=600.0)
    cb.record_failure("a")  # open 'a'

    async def ok() -> str:
        return "A"

    # 'a' circuit is open, but it is the only candidate → last-resort attempt.
    out = await call_with_fallback([("a", ok)], breaker=cb)
    assert out == "A"


@pytest.mark.asyncio
async def test_call_with_fallback_raises_when_all_fail() -> None:
    """When every provider fails, the last error propagates."""
    async def boom_a() -> str:
        raise RuntimeError("a-down")

    async def boom_b() -> str:
        raise RuntimeError("b-down")

    cb = CircuitBreaker()
    with pytest.raises(RuntimeError):
        await call_with_fallback([("a", boom_a), ("b", boom_b)], breaker=cb)

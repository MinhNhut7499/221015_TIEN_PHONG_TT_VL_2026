"""Per-provider circuit breaker + fallback runner (A4b robustness).

When an LLM provider (Gemini / OpenAI / Grok) has a *long* outage, retrying it on
every call wastes a full timeout each time. The circuit breaker tracks
consecutive failures per provider key; after ``CIRCUIT_FAIL_THRESHOLD`` it
"opens" the circuit for ``CIRCUIT_COOLDOWN_SEC`` so further calls to that
provider fail fast (skipped), letting a fallback provider answer immediately.
A single success closes the circuit again. State is in-memory and shared at the
module level so it persists across requests within one process (the value is
mainly seen across a batch run, e.g. evaluating 200 images while one provider is
down).

``call_with_fallback`` tries an ordered list of (provider_key, coroutine
factory) candidates, skipping providers whose circuit is open, until one
succeeds. This is used ONLY for stages where swapping providers is safe — the
evidence extraction (Stage A) and the arbiter (Stage E) — never to substitute a
panel judge (that would make two judges share a provider and break the panel's
independence).
"""
import logging
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, List, Optional, Tuple, TypeVar

from app.config import settings

logger = logging.getLogger(__name__)

_T = TypeVar("_T")


@dataclass
class _BreakerState:
    """Per-provider failure counter and open-until timestamp (monotonic)."""

    fails: int = 0
    open_until: float = 0.0


class CircuitBreaker:
    """Tracks per-provider consecutive failures and opens on a threshold."""

    def __init__(
        self,
        fail_threshold: Optional[int] = None,
        cooldown_sec: Optional[float] = None,
    ) -> None:
        """Initialise with thresholds (defaults from settings)."""
        self._threshold = (
            fail_threshold if fail_threshold is not None
            else settings.CIRCUIT_FAIL_THRESHOLD
        )
        self._cooldown = (
            cooldown_sec if cooldown_sec is not None
            else settings.CIRCUIT_COOLDOWN_SEC
        )
        self._states: dict[str, _BreakerState] = {}

    def is_open(self, key: str) -> bool:
        """Return True if this provider's circuit is currently open (skip it)."""
        state = self._states.get(key)
        if state is None:
            return False
        return bool(state.open_until) and time.monotonic() < state.open_until

    def record_success(self, key: str) -> None:
        """Reset a provider's failure count (circuit closed)."""
        self._states[key] = _BreakerState()

    def record_failure(self, key: str) -> None:
        """Increment a provider's failure count, opening the circuit on threshold."""
        state = self._states.setdefault(key, _BreakerState())
        state.fails += 1
        if state.fails >= self._threshold and not (
            state.open_until and time.monotonic() < state.open_until
        ):
            state.open_until = time.monotonic() + self._cooldown
            logger.warning(
                "Circuit OPEN for provider %r after %d consecutive failures; "
                "skipping it for %.0fs",
                key,
                state.fails,
                self._cooldown,
            )

    def reset(self) -> None:
        """Clear all breaker state (used by tests)."""
        self._states.clear()


# Module-level singleton shared across requests/stages within the process.
_breaker = CircuitBreaker()


def get_circuit_breaker() -> CircuitBreaker:
    """Return the shared process-wide circuit breaker."""
    return _breaker


async def call_with_fallback(
    candidates: List[Tuple[str, Callable[[], Awaitable[_T]]]],
    breaker: Optional[CircuitBreaker] = None,
) -> _T:
    """Try each (provider_key, factory) in order until one succeeds.

    Providers whose circuit is open are skipped (fail fast). A successful call
    closes that provider's circuit; a failing call records a failure and the
    next candidate is tried. If every provider's circuit is open, the chain is
    attempted once more ignoring the open state (last resort — better a slow
    answer than none).

    Args:
        candidates: Ordered (provider_key, async factory) pairs, primary first.
        breaker: Circuit breaker to use (defaults to the shared singleton).

    Returns:
        The first successful factory result.

    Raises:
        Exception: The last failure if every candidate failed, or RuntimeError
            when the candidate list is empty.
    """
    breaker = breaker or _breaker
    last_exc: Optional[BaseException] = None
    attempted = False

    for key, factory in candidates:
        if breaker.is_open(key):
            continue
        attempted = True
        try:
            result = await factory()
            breaker.record_success(key)
            return result
        except Exception as exc:  # noqa: BLE001 — boundary: try the next provider
            breaker.record_failure(key)
            last_exc = exc
            logger.warning("Provider %r failed; trying fallback: %s", key, exc)

    if not attempted:
        # Every circuit was open — try the chain anyway as a last resort.
        for key, factory in candidates:
            try:
                result = await factory()
                breaker.record_success(key)
                return result
            except Exception as exc:  # noqa: BLE001 — boundary: last-resort attempt
                breaker.record_failure(key)
                last_exc = exc

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("call_with_fallback: no provider candidates supplied")

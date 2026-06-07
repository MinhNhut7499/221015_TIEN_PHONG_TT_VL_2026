"""Provider-agnostic retry helper for transient LLM API failures.

The three LLM services (Gemini, DeepSeek, OpenAI) all hit the network and
periodically return transient errors — most commonly HTTP 503 "model
overloaded" (Gemini) and 429 rate limits. These succeed on a short retry.

``with_retry`` wraps a coroutine factory with bounded exponential backoff +
jitter, retrying only on errors classified transient by ``is_transient``.
Non-transient errors (auth, bad request, value errors) propagate immediately
so genuine bugs are not masked. The total backoff is intentionally small so a
call stays within the per-agent ``asyncio.wait_for`` timeout.
"""
import asyncio
import logging
import random
from typing import Awaitable, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# HTTP status codes worth retrying (transient server / throttling errors).
_TRANSIENT_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}

# Substrings that indicate a transient condition when no status code is exposed.
_TRANSIENT_MARKERS = (
    "overloaded",
    "unavailable",
    "rate limit",
    "ratelimit",
    "resource_exhausted",
    "too many requests",
    "try again",
    "temporarily",
    "timeout",
    "timed out",
    "503",
    "429",
    "500",
    "502",
    "504",
)


def is_transient(exc: BaseException) -> bool:
    """Return True if ``exc`` looks like a transient, retryable LLM API error.

    Checks (in order): an asyncio timeout, a numeric ``status_code``/``code``
    attribute exposed by the SDK, then a case-insensitive marker scan of the
    string representation. Provider-agnostic — no SDK error classes imported.
    """
    if isinstance(exc, asyncio.TimeoutError):
        return True
    for attr in ("status_code", "code", "http_status"):
        value = getattr(exc, attr, None)
        if isinstance(value, int) and value in _TRANSIENT_STATUS_CODES:
            return True
    message = str(exc).lower()
    return any(marker in message for marker in _TRANSIENT_MARKERS)


async def with_retry(
    factory: Callable[[], Awaitable[T]],
    *,
    attempts: int,
    base_delay: float,
    max_delay: float = 8.0,
) -> T:
    """Await ``factory()`` with retry on transient errors.

    Args:
        factory: Zero-argument callable returning a fresh awaitable each call
            (a new awaitable is required per attempt — awaitables are
            single-use).
        attempts: Total number of attempts (>= 1). ``attempts=1`` disables retry.
        base_delay: Base backoff in seconds; attempt i waits
            ``base_delay * 2**i`` plus random jitter, capped at ``max_delay``.
        max_delay: Upper bound on a single backoff sleep.

    Returns:
        The result of the first successful ``factory()`` await.

    Raises:
        The last exception raised by ``factory()`` if all attempts fail or the
        error is non-transient.
    """
    total = max(1, attempts)
    for index in range(total):
        try:
            return await factory()
        except Exception as exc:  # noqa: BLE001 — re-raised below; classified first.
            if index == total - 1 or not is_transient(exc):
                raise
            delay = min(max_delay, base_delay * (2 ** index)) + random.uniform(
                0.0, base_delay
            )
            logger.warning(
                "Transient LLM error (attempt %d/%d), retrying in %.2fs: %s",
                index + 1,
                total,
                delay,
                exc,
            )
            await asyncio.sleep(delay)
    # Unreachable: the loop either returns or raises on the final attempt.
    raise RuntimeError("with_retry exhausted attempts without returning")

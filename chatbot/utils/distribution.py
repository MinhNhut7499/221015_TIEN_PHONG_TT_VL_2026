"""Helpers for building a validated :class:`StyleDistribution` from raw LLM JSON.

Shared by the judging panel (each judge's verdict) and the arbiter in the
pipeline runner, so it lives here rather than in either module to avoid an
import cycle.
"""
from typing import Any, Dict, Optional

from chatbot.utils.schemas import StyleDistribution

SECONDARY_THRESHOLD = 0.15
"""Minimum normalised probability for a style to enter ``StyleDistribution.secondary``."""


def safe_float(value: Any, default: float = 0.0) -> float:
    """Convert an arbitrary JSON-decoded value to float, falling back on failure."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_style_distribution_safe(
    raw: Dict[str, Any],
    fallback_primary: str,
    allowed: Optional[set] = None,
) -> StyleDistribution:
    """Construct a validated StyleDistribution from a raw LLM-emitted dict.

    When ``allowed`` is given, only those candidate style names are kept (matched
    case-insensitively and mapped back to the canonical candidate spelling) —
    this keeps a judge/arbiter constrained to the KB candidate set. When
    ``allowed`` is None, any non-empty style name is accepted (open vocabulary).

    Values are coerced to non-negative floats, normalised to sum=1.0, then
    ``primary`` (argmax) and ``secondary`` (≥ ``SECONDARY_THRESHOLD``) computed.
    Falls back to a 1-hot on ``fallback_primary`` if nothing valid remains.
    """
    canon = {a.lower(): a for a in allowed} if allowed else None
    cleaned: Dict[str, float] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not key.strip():
            continue
        name = key.strip()
        if canon is not None:
            mapped = canon.get(name.lower())
            if mapped is None:
                continue
            name = mapped
        prob = max(0.0, safe_float(value, default=0.0))
        if prob > 0:
            cleaned[name] = cleaned.get(name, 0.0) + prob
    if not cleaned:
        cleaned = {fallback_primary: 1.0}
    total = sum(cleaned.values())
    normalised = {k: v / total for k, v in cleaned.items()}
    primary = max(normalised, key=normalised.get)
    secondary = sorted(
        (s for s, p in normalised.items() if s != primary and p >= SECONDARY_THRESHOLD),
        key=lambda s: -normalised[s],
    )
    return StyleDistribution(distribution=normalised, primary=primary, secondary=secondary)

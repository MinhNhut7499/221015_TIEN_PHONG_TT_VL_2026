"""Numeric fusion of evidence streams into a style distribution.

This is the deterministic, hand-weighted fuser used as:
- an ANCHOR injected into the Agent 5/7 prompts ("start from this prior"), and
- a FALLBACK when the LLM fusion (Tier 2) is unavailable.

It blends three streams over ``STYLE_CLASSES``:
- ``votes_norm``  — normalised aggregated component votes (YOLO + Agent 2)
- ``style_prior`` — CNN P(style|image) from the ResNet50 head
- ``attribute_affinity`` — hand-crafted attribute cosine (TIE-BREAKER, small weight)

Material is intentionally NOT fused here — it is a coarse 5-class signal over a
different label space and already feeds the rule layer + LLM prompt.

A learned, calibrated fuser (``FuserService``) supersedes this when
``models/fuser.joblib`` exists; ``numeric_fuse`` remains the cold-start path.
"""
from typing import Dict, Optional

from chatbot.utils.schemas import STYLE_CLASSES


def _as_distribution(scores: Optional[Dict[str, float]]) -> Optional[Dict[str, float]]:
    """Project a score dict onto STYLE_CLASSES and normalise to sum=1.

    Returns None when the input is missing or carries no positive mass (so the
    caller can redistribute that stream's weight to the available streams).
    """
    if not scores:
        return None
    clean = {s: max(0.0, float(scores.get(s, 0.0))) for s in STYLE_CLASSES}
    total = sum(clean.values())
    if total <= 0.0:
        return None
    return {s: v / total for s, v in clean.items()}


def numeric_fuse(
    votes_norm: Optional[Dict[str, float]],
    style_prior: Optional[Dict[str, float]],
    attribute_affinity: Optional[Dict[str, float]],
    *,
    weight_votes: float,
    weight_prior: float,
    weight_attribute: float,
) -> Dict[str, float]:
    """Blend the three streams into a normalised style distribution.

    Each stream is first projected to a probability distribution. Streams that
    are missing or empty are dropped and their weight is renormalised across
    the remaining streams (so a down stream does not silently shrink the
    output mass). If no stream is available the result is uniform.

    Returns:
        ``{style: probability}`` over ``STYLE_CLASSES`` summing to 1.0.
    """
    sources = [
        (_as_distribution(votes_norm), weight_votes),
        (_as_distribution(style_prior), weight_prior),
        (_as_distribution(attribute_affinity), weight_attribute),
    ]
    active = [(dist, w) for dist, w in sources if dist is not None and w > 0]
    if not active:
        uniform = 1.0 / len(STYLE_CLASSES)
        return {s: uniform for s in STYLE_CLASSES}

    weight_total = sum(w for _, w in active)
    fused = {s: 0.0 for s in STYLE_CLASSES}
    for dist, w in active:
        scale = w / weight_total
        for s in STYLE_CLASSES:
            fused[s] += scale * dist[s]
    total = sum(fused.values()) or 1.0
    return {s: v / total for s, v in fused.items()}

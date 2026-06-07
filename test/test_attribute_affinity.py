"""Unit tests for STYLE_ATTRIBUTE_PROFILES + compute_attribute_affinity.

Covers:
- Schema completeness: every entry in ``STYLE_CLASSES`` has a profile.
- Self-similarity: observed = profile_X → top affinity = X.
- Discrimination: profiles that should differ strongly actually differ
  (e.g. Brutalism vs Baroque).
- Edge cases: zero vector input, ambiguous mid-range input.

Run with:
    pytest test/test_attribute_affinity.py -v
"""
import pytest

from chatbot.utils.rule_checker import (
    STYLE_ATTRIBUTE_PROFILES,
    compute_attribute_affinity,
)
from chatbot.utils.schemas import STYLE_CLASSES, AttributeVector


# ── Profile catalogue invariants ──────────────────────────────────────────────

def test_every_style_has_a_profile() -> None:
    """All 10 style names in STYLE_CLASSES must have a profile entry."""
    assert set(STYLE_ATTRIBUTE_PROFILES.keys()) == set(STYLE_CLASSES)


def test_profile_values_are_in_expected_ranges() -> None:
    """Profile fields should respect the AttributeVector value ranges."""
    for style, profile in STYLE_ATTRIBUTE_PROFILES.items():
        for field in (
            "symmetry_score",
            "vertical_dominance",
            "horizontal_dominance",
            "curvature_score",
            "surface_roughness",
            "edge_density",
        ):
            value = getattr(profile, field)
            assert 0.0 <= value <= 1.0, f"{style}.{field}={value} out of [0,1]"
        assert 0.0 <= profile.edge_orientation_entropy <= 3.0, (
            f"{style}.edge_orientation_entropy out of expected range"
        )


# ── Self-similarity ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("style", STYLE_CLASSES)
def test_profile_self_similarity_picks_itself(style: str) -> None:
    """Feeding profile X as observation must produce X as top affinity."""
    profile = STYLE_ATTRIBUTE_PROFILES[style]
    affinity = compute_attribute_affinity(profile)
    top_style = max(affinity, key=affinity.get)
    assert top_style == style, (
        f"Expected {style} as top affinity but got {top_style} "
        f"(scores: {sorted(affinity.items(), key=lambda kv: -kv[1])[:3]})"
    )
    assert affinity[style] > 0.99, (
        f"Self-similarity for {style} should be ≈1.0, got {affinity[style]}"
    )


# ── Discrimination between distinct profiles ──────────────────────────────────

def test_brutalism_observation_outranks_baroque() -> None:
    """Brutalism prototype must score higher for itself than for Baroque."""
    affinity = compute_attribute_affinity(STYLE_ATTRIBUTE_PROFILES["Brutalism"])
    assert affinity["Brutalism"] > affinity["Baroque"]


def test_neoclassical_observation_outranks_deconstructivism() -> None:
    """Neoclassical (high symmetry) vs Deconstructivism (low symmetry)."""
    affinity = compute_attribute_affinity(
        STYLE_ATTRIBUTE_PROFILES["Neoclassical"]
    )
    assert affinity["Neoclassical"] > affinity["Deconstructivism"]


def test_gothic_observation_outranks_modernism() -> None:
    """Gothic (vertical + ornament) vs Modernism (horizontal + sparse)."""
    affinity = compute_attribute_affinity(STYLE_ATTRIBUTE_PROFILES["Gothic"])
    assert affinity["Gothic"] > affinity["Modernism"]


# ── Edge cases ────────────────────────────────────────────────────────────────

def test_zero_vector_returns_all_zeros() -> None:
    """An all-zero observation has no direction; affinity must be 0 for all."""
    zero = AttributeVector(
        symmetry_score=0.0,
        vertical_dominance=0.0,
        horizontal_dominance=0.0,
        curvature_score=0.0,
        surface_roughness=0.0,
        edge_density=0.0,
        edge_orientation_entropy=0.0,
    )
    affinity = compute_attribute_affinity(zero)
    assert set(affinity.keys()) == set(STYLE_CLASSES)
    for style, score in affinity.items():
        assert score == 0.0, f"{style} scored {score} for zero input"


def test_affinity_values_in_unit_interval() -> None:
    """Returned scores must always lie in [0, 1]."""
    arbitrary = AttributeVector(
        symmetry_score=0.3,
        vertical_dominance=0.6,
        horizontal_dominance=0.7,
        curvature_score=0.4,
        surface_roughness=0.5,
        edge_density=0.5,
        edge_orientation_entropy=2.0,
    )
    affinity = compute_attribute_affinity(arbitrary)
    for style, score in affinity.items():
        assert 0.0 <= score <= 1.0, f"{style}={score} out of [0,1]"


def test_affinity_is_deterministic() -> None:
    """Same observation → same affinity dict."""
    obs = STYLE_ATTRIBUTE_PROFILES["Art Deco"]
    first = compute_attribute_affinity(obs)
    second = compute_attribute_affinity(obs)
    assert first == second

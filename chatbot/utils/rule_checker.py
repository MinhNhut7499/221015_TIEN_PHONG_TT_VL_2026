"""Agent 3a: Hard rule checker for architectural style ↔ component + material consistency.

Pure code — no LLM calls. Lookups against HARD_RULES and MATERIAL_STYLE_RULES
flag contradictions; Agent 3b (DeepSeek) interprets them.

The module also exposes ``STYLE_ATTRIBUTE_PROFILES`` and
``compute_attribute_affinity`` for the multi-style mixture pipeline: each
style is represented by a prototype ``AttributeVector`` and an image's
observed attributes are scored against every prototype via cosine
similarity. The 10-dim affinity vector is then injected into Agent 5/7
prompts as one of four independent evidence streams (alongside YOLO
component votes, material classification and CNN style prior).
"""
import math
from typing import Dict, List, Optional

import numpy as np

from chatbot.utils.schemas import Agent3Output, AttributeVector, STYLE_CLASSES


# Maps each style to the component types that are COMPATIBLE (expected) for that style.
# A component_type that appears as the top-voted style's components is NOT a contradiction.
# A component_type that strongly signals a DIFFERENT style IS a contradiction.
HARD_RULES: Dict[str, List[str]] = {
    "Gothic":           ["arch", "spire"],
    "Baroque":          ["dome", "arch", "pediment", "column_capital",
                         "solomonic_column", "curved_iron_balcony"],
    "Renaissance":      ["dome", "arch", "pediment", "column_capital"],
    "Neoclassical":     ["dome", "pediment", "column_capital"],
    "Art Nouveau":      ["curved_iron_balcony"],
    "Art Deco":         ["flat_roof"],
    "Modernism":        ["flat_roof"],
    "Deconstructivism": ["flat_roof"],
    "Brutalism":        ["flat_roof"],
    "High-tech":        [],
}

# Component types that are strongly exclusive to one or more style families.
# If the top-voted style is NOT in the list of compatible styles for a component,
# it is flagged as a contradiction. Components shared across many styles
# (arch, dome, pediment, column_capital, spire, curved_iron_balcony, flat_roof)
# are NOT listed here — they go through Agent 1's geometric analysis instead.
_EXCLUSIVE_COMPONENTS: Dict[str, List[str]] = {
    "solomonic_column": ["Baroque"],
}

# Maps each material to the architectural styles that typically/historically
# use that material as their dominant exterior surface. Used by
# check_material_consistency() to flag mismatch between YOLOv8s-cls output
# and the leading style hypothesis.
MATERIAL_STYLE_RULES: Dict[str, List[str]] = {
    "concrete": ["Brutalism", "Deconstructivism", "Modernism", "Art Deco"],
    "glass":    ["High-tech", "Modernism", "Deconstructivism"],
    "stone":    ["Gothic", "Renaissance", "Neoclassical", "Baroque",
                 "Art Deco", "Art Nouveau"],
    "brick":    ["Modernism", "Baroque", "Renaissance", "Art Nouveau"],
    "metal":    ["High-tech", "Deconstructivism", "Art Deco"],
}


def check_rules(component_type: str, top_style: str) -> Agent3Output:
    """Agent 3a: determine if a component type contradicts the predicted top style.

    Logic:
    1. If component_type is in _EXCLUSIVE_COMPONENTS and top_style is NOT in
       its compatible styles list → hard contradiction.
    2. Otherwise → no contradiction.

    Args:
        component_type: YOLO-detected component type label.
        top_style: Highest-scoring style from Agent 2.

    Returns:
        Agent3Output with has_contradiction and explanation.
    """
    exclusive_styles = _EXCLUSIVE_COMPONENTS.get(component_type)

    if exclusive_styles and top_style not in exclusive_styles:
        styles_str = " or ".join(exclusive_styles)
        violated = [
            f"{component_type} is strongly associated with {styles_str}, "
            f"not {top_style}"
        ]
        return Agent3Output(
            component_id="",
            has_contradiction=True,
            contradiction_analysis=(
                f"Component '{component_type}' is architecturally exclusive to "
                f"'{styles_str}' style(s), but the predicted style is '{top_style}'. "
                "This may indicate a misclassification or an eclectic building."
            ),
            violated_rules=violated,
        )

    return Agent3Output(
        component_id="",
        has_contradiction=False,
        contradiction_analysis="No hard rule violations detected.",
        violated_rules=[],
    )


def check_material_consistency(
    dominant_material: str, top_style: str
) -> Optional[str]:
    """Check whether the YOLOv8s-cls dominant material is compatible with top_style.

    Lookup MATERIAL_STYLE_RULES[dominant_material]. If top_style is not in the
    compatible list, return a contradiction message; otherwise return None.

    Args:
        dominant_material: Top material from MaterialDistribution.dominant.
        top_style: Leading style hypothesis from Agent 5 or vote table.

    Returns:
        Contradiction message string if inconsistent, else None.
    """
    compatible_styles = MATERIAL_STYLE_RULES.get(dominant_material)
    if compatible_styles is None:
        return None
    if top_style in compatible_styles:
        return None
    styles_str = ", ".join(compatible_styles)
    return (
        f"Material '{dominant_material}' is uncommon for style '{top_style}'. "
        f"It typically appears in: {styles_str}."
    )


# ── Multi-style mixture: attribute prototypes + affinity scoring ──────────────

# Prototype AttributeVector for each of the 10 styles. Numeric values encode
# the qualitative profile in the Multi-Style Mixture Analysis plan:
#   0.10 / 0.25 / 0.50 / 0.70 / 0.85 / 0.95 ≈ very low / low / medium / high /
#   very high / extreme for 0-1 ranged fields.
# edge_orientation_entropy uses the natural-log scale 0 – log(18) ≈ 2.89
# where low values denote clustered orientations (geometric ornament) and
# high values denote spread orientations (organic curves).
STYLE_ATTRIBUTE_PROFILES: Dict[str, AttributeVector] = {
    "Gothic": AttributeVector(
        symmetry_score=0.75,
        vertical_dominance=0.85,
        horizontal_dominance=0.20,
        curvature_score=0.55,
        surface_roughness=0.50,
        edge_density=0.70,
        edge_orientation_entropy=1.80,
    ),
    "Baroque": AttributeVector(
        symmetry_score=0.65,
        vertical_dominance=0.55,
        horizontal_dominance=0.50,
        curvature_score=0.80,
        surface_roughness=0.60,
        edge_density=0.85,
        edge_orientation_entropy=2.30,
    ),
    "Renaissance": AttributeVector(
        symmetry_score=0.85,
        vertical_dominance=0.55,
        horizontal_dominance=0.55,
        curvature_score=0.45,
        surface_roughness=0.50,
        edge_density=0.55,
        edge_orientation_entropy=1.90,
    ),
    "Neoclassical": AttributeVector(
        symmetry_score=0.92,
        vertical_dominance=0.70,
        horizontal_dominance=0.45,
        curvature_score=0.35,
        surface_roughness=0.30,
        edge_density=0.40,
        edge_orientation_entropy=1.50,
    ),
    "Art Nouveau": AttributeVector(
        symmetry_score=0.45,
        vertical_dominance=0.55,
        horizontal_dominance=0.50,
        curvature_score=0.75,
        surface_roughness=0.55,
        edge_density=0.70,
        edge_orientation_entropy=2.50,
    ),
    "Art Deco": AttributeVector(
        symmetry_score=0.85,
        vertical_dominance=0.75,
        horizontal_dominance=0.40,
        curvature_score=0.30,
        surface_roughness=0.40,
        edge_density=0.60,
        edge_orientation_entropy=1.20,
    ),
    "Modernism": AttributeVector(
        symmetry_score=0.65,
        vertical_dominance=0.40,
        horizontal_dominance=0.70,
        curvature_score=0.20,
        surface_roughness=0.25,
        edge_density=0.20,
        edge_orientation_entropy=1.50,
    ),
    "Deconstructivism": AttributeVector(
        symmetry_score=0.20,
        vertical_dominance=0.45,
        horizontal_dominance=0.45,
        curvature_score=0.30,
        surface_roughness=0.55,
        edge_density=0.40,
        edge_orientation_entropy=2.40,
    ),
    "Brutalism": AttributeVector(
        symmetry_score=0.60,
        vertical_dominance=0.55,
        horizontal_dominance=0.55,
        curvature_score=0.20,
        surface_roughness=0.80,
        edge_density=0.25,
        edge_orientation_entropy=1.60,
    ),
    "High-tech": AttributeVector(
        symmetry_score=0.55,
        vertical_dominance=0.55,
        horizontal_dominance=0.55,
        curvature_score=0.25,
        surface_roughness=0.30,
        edge_density=0.30,
        edge_orientation_entropy=1.30,
    ),
}

# Maximum value of edge_orientation_entropy with 18 histogram bins. Used to
# rescale that field into [0, 1] before cosine similarity so it carries
# comparable weight to the other six attributes.
_ENTROPY_SCALE = math.log(18)


def _attribute_to_array(vec: AttributeVector) -> np.ndarray:
    """Convert AttributeVector → 7-dim float64 array with entropy rescaled.

    edge_orientation_entropy is divided by log(18) so all seven dimensions
    lie in roughly [0, 1] and contribute comparably to cosine similarity.
    """
    return np.array(
        [
            vec.symmetry_score,
            vec.vertical_dominance,
            vec.horizontal_dominance,
            vec.curvature_score,
            vec.surface_roughness,
            vec.edge_density,
            vec.edge_orientation_entropy / _ENTROPY_SCALE,
        ],
        dtype=np.float64,
    )


# Per-dimension mean/std of the 10 style prototypes (after entropy rescale).
# Used to STANDARDISE both the observed vector and each profile before cosine,
# so the comparison reflects deviation-from-average rather than the raw
# (all-positive) magnitudes — otherwise the large dims (vertical_dominance,
# edge_density) dominate cosine and wash out the discriminating dims
# (curvature, symmetry, entropy). See decision #54 / #58.
_PROFILE_MATRIX = np.stack(
    [_attribute_to_array(STYLE_ATTRIBUTE_PROFILES[s]) for s in STYLE_CLASSES]
)
_PROFILE_MEAN = _PROFILE_MATRIX.mean(axis=0)
_PROFILE_STD = _PROFILE_MATRIX.std(axis=0)
_PROFILE_STD[_PROFILE_STD < 1e-9] = 1e-9  # guard against zero-variance dims


def _standardise(arr: np.ndarray) -> np.ndarray:
    """Z-score a 7-dim attribute array against the prototype population stats."""
    return (arr - _PROFILE_MEAN) / _PROFILE_STD


def compute_attribute_affinity(observed: AttributeVector) -> Dict[str, float]:
    """Affinity between observed attributes and each style prototype.

    Both the observed vector and every prototype are STANDARDISED per-dimension
    (z-score vs the 10-prototype population) before cosine similarity, then the
    cosine in ``[-1, 1]`` is mapped to ``[0, 1]`` via ``(c + 1) / 2``. Centering
    makes the score reflect how the building DEVIATES from the average style
    profile, so discriminating dimensions (curvature, symmetry, entropy) carry
    weight instead of being washed out by the always-large dims.

    Values are NOT normalised to sum to 1 — multiple styles can score high when
    genuinely ambiguous. This is a TIE-BREAKER signal (hand-crafted, low
    discriminative power), not a primary classifier.

    Args:
        observed: AttributeVector produced by
            ``chatbot.utils.cv_attributes.extract_attributes``.

    Returns:
        Mapping ``{style_name: affinity in [0, 1]}`` for every style in
        ``STYLE_CLASSES``. If ``observed`` is the zero vector all values
        are 0.0.
    """
    raw = _attribute_to_array(observed)
    if float(np.linalg.norm(raw)) < 1e-9:
        return {style: 0.0 for style in STYLE_CLASSES}
    obs_z = _standardise(raw)
    obs_norm = float(np.linalg.norm(obs_z))
    affinity: Dict[str, float] = {}
    for style in STYLE_CLASSES:
        prof_z = _standardise(_attribute_to_array(STYLE_ATTRIBUTE_PROFILES[style]))
        prof_norm = float(np.linalg.norm(prof_z))
        if obs_norm < 1e-9 or prof_norm < 1e-9:
            affinity[style] = 0.0
            continue
        cosine = float((obs_z * prof_z).sum() / (obs_norm * prof_norm))
        affinity[style] = max(0.0, min(1.0, (cosine + 1.0) / 2.0))
    return affinity


def check_prior_vote_agreement(
    votes_norm: Dict[str, float],
    style_prior: Dict[str, float],
) -> Optional[str]:
    """Flag low agreement between component votes and the CNN style prior.

    Both are independent evidence streams over ``STYLE_CLASSES``. When their
    argmax styles differ — and the vote table actually carries mass — the two
    detectors disagree about the leading style. This returns a human-readable
    note (consumed by Agent 7's prompt) so the LLM weighs the whole image more
    heavily instead of over-committing to either stream. It is a SOFT signal —
    it never overrides a decision, avoiding the failure mode where a wrong CNN
    prior vetoes correct component detections (and vice-versa).

    Args:
        votes_norm: Normalised aggregated component votes (sum ≤ 1.0).
        style_prior: CNN P(style|image) from the ResNet50 head.

    Returns:
        A disagreement note, or None when the streams agree / votes are empty.
    """
    if not votes_norm or not style_prior:
        return None
    vote_top = max(votes_norm, key=votes_norm.get)
    if votes_norm[vote_top] <= 0.0:
        return None
    prior_top = max(style_prior, key=style_prior.get)
    if vote_top == prior_top:
        return None
    return (
        f"Component votes favour '{vote_top}' ({votes_norm[vote_top]:.2f}) but the "
        f"CNN global prior favours '{prior_top}' ({style_prior[prior_top]:.2f}). "
        "Treat this as LOW cross-stream agreement: weigh the full image heavily "
        "and prefer a mixture over fully committing to either stream."
    )

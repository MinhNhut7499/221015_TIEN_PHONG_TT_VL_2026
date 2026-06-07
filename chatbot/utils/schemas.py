"""Pydantic schemas for the 7-agent architecture analysis pipeline.

These models form the contract between:
- MockYOLOService / RealYOLOService → pipeline (DetectedComponent)
- MockMaterialClassifierService → pipeline (MaterialDistribution)
- MockGlobalFeatureService / RealGlobalFeatureService → pipeline (GlobalFeatureOutput)
- Agent outputs within pipeline_runner (Agent1Output … Agent6Output)
- Router response (FinalAnalysisResult → AnalyzeResponse)

YOLO contract (DetectedComponent) is frozen — do not change fields when
implementing RealYOLOService.detect(). Other schemas may be extended for
new evidence streams (e.g. GlobalFeatureOutput for CNN backbone + CV
attributes) following the additive pattern below.
"""
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ── YOLO component types (finalized — do not add/remove) ──────────────────────

ComponentType = Literal[
    "arch",
    "spire",
    "dome",
    "pediment",
    "column_capital",
    "solomonic_column",
    "curved_iron_balcony",
    "flat_roof",
]

COMPONENT_TYPES: List[str] = list(ComponentType.__args__)  # type: ignore[attr-defined]


# ── YOLOv8s-cls material types (finalized — do not add/remove) ────────────────

MaterialType = Literal[
    "concrete",
    "glass",
    "stone",
    "brick",
    "metal",
]

MATERIAL_CLASSES: List[str] = list(MaterialType.__args__)  # type: ignore[attr-defined]


# ── Architectural style classes (finalized — do not add/remove) ───────────────

STYLE_CLASSES: List[str] = [
    "Gothic",
    "Baroque",
    "Renaissance",
    "Neoclassical",
    "Art Nouveau",
    "Art Deco",
    "Modernism",
    "Deconstructivism",
    "Brutalism",
    "High-tech",
]


# ── YOLO ↔ Pipeline contract ──────────────────────────────────────────────────

class BoundingBox(BaseModel):
    """Pixel coordinates of a detected component's bounding box."""

    x_min: int
    y_min: int
    x_max: int
    y_max: int


class DetectedComponent(BaseModel):
    """One component detected by YOLO (or MockYOLO during development).

    crop_base64 and full_image_base64 are JPEG images encoded as base64 strings.
    """

    component_id: str
    component_type: ComponentType
    detection_confidence: float
    bounding_box: BoundingBox
    crop_base64: str
    full_image_base64: str

    @field_validator("detection_confidence")
    @classmethod
    def confidence_in_range(cls, v: float) -> float:
        """Ensure confidence is between 0 and 1."""
        if not 0.0 <= v <= 1.0:
            raise ValueError("detection_confidence must be between 0.0 and 1.0")
        return v


class MaterialDistribution(BaseModel):
    """Output of the YOLOv8s-cls material classifier for a single image.

    The classifier runs once per image (not per component) and returns the
    probability distribution over the 5 MaterialType classes. ``dominant`` is
    the top-1 material and ``confidence`` is its probability — both are
    convenience fields derived from ``distribution``.

    ``observed_materials`` is an optional free-text list of the materials a
    vision backend (e.g. GeminiMaterialClassifierService) actually observed —
    possibly outside the 5 controlled classes (e.g. ``"weathered steel"``,
    ``"terracotta"``). It is context for the downstream LLM agents only and is
    NOT used by the deterministic rule layer (``check_material_consistency``).
    """

    distribution: Dict[str, float]
    dominant: str
    confidence: float
    observed_materials: List[str] = Field(default_factory=list)

    @field_validator("confidence")
    @classmethod
    def confidence_in_range(cls, v: float) -> float:
        """Ensure confidence is between 0 and 1."""
        if not 0.0 <= v <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        return v


# ── Multi-style mixture + global feature schemas ──────────────────────────────

class StyleDistribution(BaseModel):
    """Mixture distribution over the 10 architectural styles.

    Models style as a continuous mixture instead of a single label. Keys of
    ``distribution`` are validated against STYLE_CLASSES; unknown keys are
    dropped, negatives clipped to 0, and remaining values normalised to
    sum=1.0. ``primary`` is the argmax style. ``secondary`` lists every style
    with probability ≥ 0.15, ranked by descending probability (excluding
    primary). This is the contract used by Agent 4/5/7 outputs.
    """

    distribution: Dict[str, float]
    primary: str
    secondary: List[str]

    @field_validator("distribution")
    @classmethod
    def normalise_distribution(cls, v: Dict[str, float]) -> Dict[str, float]:
        """Filter unknown styles, clip negatives, renormalise to sum=1.0."""
        cleaned = {k: max(0.0, val) for k, val in v.items() if k in STYLE_CLASSES}
        total = sum(cleaned.values())
        if total <= 0:
            raise ValueError(
                "StyleDistribution must contain at least one style with positive probability"
            )
        return {k: val / total for k, val in cleaned.items()}

    @field_validator("primary")
    @classmethod
    def primary_in_styles(cls, v: str) -> str:
        """Ensure primary is one of the 10 valid styles."""
        if v not in STYLE_CLASSES:
            raise ValueError(f"primary must be one of {STYLE_CLASSES}, got {v!r}")
        return v


class AttributeVector(BaseModel):
    """Seven interpretable visual attributes from classical CV.

    All values come from pure OpenCV/numpy/scikit-image — no model training
    required. Used by Agent 2/5/7 prompts and by ``compute_attribute_affinity``
    in ``rule_checker`` for cosine similarity against STYLE_ATTRIBUTE_PROFILES.

    Ranges:
    - symmetry_score, vertical_dominance, horizontal_dominance,
      curvature_score, surface_roughness, edge_density: 0.0 – 1.0
    - edge_orientation_entropy: 0.0 – log(n_orientation_bins); unbounded above
    """

    symmetry_score: float
    vertical_dominance: float
    horizontal_dominance: float
    curvature_score: float
    surface_roughness: float
    edge_density: float
    edge_orientation_entropy: float


class GlobalFeatureOutput(BaseModel):
    """Output of the global feature extractor (ResNet50 + CV attributes).

    Bundles the three image-level signals produced by GlobalFeatureService:
    - ``style_prior``: 10-class softmax from frozen ResNet50 + Linear head.
      Treated as P(style|image) PRIOR, not a classification decision.
    - ``attributes``: 7-dim handcrafted geometric/textural vector.
    - ``gradcam_b64``: optional Grad-CAM heatmap overlay (PNG, base64),
      populated when ENABLE_GRADCAM is True.
    """

    style_prior: Dict[str, float]
    attributes: AttributeVector
    gradcam_b64: Optional[str] = None

    @field_validator("style_prior")
    @classmethod
    def normalise_prior(cls, v: Dict[str, float]) -> Dict[str, float]:
        """Filter unknown styles, clip negatives, renormalise to sum=1.0."""
        cleaned = {k: max(0.0, val) for k, val in v.items() if k in STYLE_CLASSES}
        total = sum(cleaned.values())
        if total <= 0:
            raise ValueError(
                "style_prior must contain at least one style with positive probability"
            )
        return {k: val / total for k, val in cleaned.items()}


# ── Pipeline contract ─────────────────────────────────────────────────────────

class PipelineInput(BaseModel):
    """Combined output of YOLOv8s-detection + YOLOv8s-cls + global feature extractor.

    ``global_features`` is Optional during the migration from the legacy
    component-only pipeline; it becomes required after Phase 3 of the
    Multi-Style Mixture Analysis plan.
    """

    components: List[DetectedComponent]
    material: MaterialDistribution
    global_features: Optional[GlobalFeatureOutput] = None
    # False when material comes from the deterministic mock (noise): downstream
    # prompts then omit the material evidence stream and the rule layer skips the
    # material-consistency check. Set True for a real classifier (e.g. gemini).
    material_available: bool = True
    # Full building image (base64 JPEG) so Agent 7 always has whole-image context
    # even when YOLO detects 0 components. Falls back to a component crop if unset.
    full_image_base64: Optional[str] = None


# ── Per-component agent outputs ────────────────────────────────────────────────

class Agent1Output(BaseModel):
    """Agent 1 (Gemini vision): geometric feature description of one component."""

    component_id: str
    feature_description: str


class Agent2Output(BaseModel):
    """Agent 2 (Gemini ×3 Monte Carlo): style probability distribution.

    style_distribution keys are from STYLE_CLASSES, values sum to ~1.0.
    """

    component_id: str
    style_distribution: Dict[str, float]
    # True when all Monte Carlo calls failed and style_distribution is a
    # placeholder uniform — such a component is excluded from vote aggregation.
    degraded: bool = False


class Agent3Output(BaseModel):
    """Agent 3a (rule check) or Agent 3b (DeepSeek fallback): contradiction analysis."""

    component_id: str
    has_contradiction: bool
    contradiction_analysis: str
    violated_rules: List[str]


class Agent4Output(BaseModel):
    """Agent 4 (DeepSeek): per-component style conclusion.

    ``style`` and ``confidence`` are the legacy single-label fields kept for
    backward compatibility during migration. ``style_distribution`` is the
    new mixture-mode field populated once the pipeline is updated to emit
    per-component distributions. When both are set they MUST agree
    (``style`` == ``style_distribution.primary``).
    """

    component_id: str
    component_type: str
    style: str
    confidence: float
    reasoning: str
    style_distribution: Optional[StyleDistribution] = None

    @field_validator("confidence")
    @classmethod
    def confidence_in_range(cls, v: float) -> float:
        """Ensure confidence is between 0 and 1."""
        if not 0.0 <= v <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        return v


class ComponentAnalysis(BaseModel):
    """Complete analysis record for one detected component (Agents 1–4).

    ``bounding_box`` carries the YOLO pixel-space box so the frontend can draw
    a detection overlay on top of the source image. Optional because legacy
    callers / tests may construct this without a box.
    """

    component_id: str
    component_type: str
    detection_confidence: float
    bounding_box: Optional[BoundingBox] = None
    agent1: Agent1Output
    agent2: Agent2Output
    agent3: Agent3Output
    agent4: Agent4Output


# ── Cross-component / final agent outputs ─────────────────────────────────────

class Agent5Output(BaseModel):
    """Agent 5 (DeepSeek): primary advocate — best style hypothesis.

    ``style``/``confidence``/``reasoning`` are the legacy single-label fields
    kept for backward compatibility. ``style_distribution`` and
    ``composition_narrative`` are populated in mixture mode (post Phase 3 of
    the Multi-Style Mixture Analysis plan).
    """

    style: str
    confidence: float
    reasoning: str
    style_distribution: Optional[StyleDistribution] = None
    composition_narrative: Optional[str] = None


class Agent6Output(BaseModel):
    """Agent 6 (DeepSeek): alternative hypothesist.

    Only receives Agent 5's label, not its reasoning, to avoid anchoring bias.
    """

    style: str
    confidence: float
    reasoning: str


class StyleCandidate(BaseModel):
    """One candidate style + its probability, used when the result is uncertain."""

    style: str
    probability: float


class FinalAnalysisResult(BaseModel):
    """Final output of the 7-agent pipeline, returned to the API router.

    Legacy fields (``style``, ``confidence``, ``explanation``, ``key_evidence``)
    are kept for backward compatibility with existing tests and DB persistence.
    Mixture-mode fields below are populated once Phase 3 of the Multi-Style
    Mixture Analysis plan lands:

    - ``style_distribution``: full 10-style mixture from Agent 7
    - ``composition_explanation``: narrative describing the mix (e.g.
      "Dominant Art Deco with Neoclassical influence because…")
    - ``evidence_per_style``: per-style supporting bullets, one list per
      style that appears in the mixture with prob ≥ 0.15
    - ``gradcam_b64``: Grad-CAM heatmap overlay forwarded from
      GlobalFeatureOutput

    Until full migration, ``style`` mirrors ``style_distribution.primary``
    and ``confidence`` mirrors its probability.
    """

    style: str
    confidence: float
    explanation: str
    key_evidence: List[str]
    components: List[ComponentAnalysis]
    agent5: Agent5Output
    agent6: Agent6Output
    processing_time_ms: float
    style_distribution: Optional[StyleDistribution] = None
    composition_explanation: Optional[str] = None
    evidence_per_style: Optional[Dict[str, List[str]]] = None
    gradcam_b64: Optional[str] = None
    # Vietnamese translations of the narrative fields, populated by the optional
    # post-Agent-7 translation pass when settings.ENABLE_BILINGUAL is True. The
    # source narrative (English) stays in the fields above; the frontend picks
    # the language. None when bilingual mode is off or translation failed.
    explanation_vi: Optional[str] = None
    key_evidence_vi: Optional[List[str]] = None
    composition_explanation_vi: Optional[str] = None
    evidence_per_style_vi: Optional[Dict[str, List[str]]] = None
    # Reliability surface: True if any evidence was lost (component dropped or
    # Agent 2 degraded); ``warnings`` lists human-readable degradation notes.
    degraded: bool = False
    warnings: List[str] = []
    # Certainty metrics derived from the final mixture (reported alongside the
    # mixture ``confidence``): margin = primary − second-best probability;
    # entropy = Shannon entropy (nats) of the distribution (lower = more certain).
    certainty_margin: Optional[float] = None
    distribution_entropy: Optional[float] = None
    # Abstention: True when the result is not confident enough (low margin/
    # entropy, or max-prob below the risk-coverage threshold). ``candidates`` is
    # the top-K of the final distribution, surfaced so the client can show
    # "uncertain — could be X / Y / Z" instead of a single forced label.
    uncertain: bool = False
    candidates: List[StyleCandidate] = []

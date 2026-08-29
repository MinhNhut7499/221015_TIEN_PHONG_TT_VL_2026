"""Pydantic schemas for the open-vocabulary architecture analysis pipeline.

These models form the contract between:
- EvidenceExtractor (Agent A) → pipeline (EvidenceSheet)
- StyleKbService → pipeline (StyleEntry candidates)
- Agent outputs within pipeline_runner (Agent5Output / Agent6Output / arbiter)
- Router response (FinalAnalysisResult → AnalyzeResponse)

Some legacy component-based schemas (DetectedComponent, ComponentAnalysis,
Agent1-4Output) are retained for response/DB shape compatibility but are no
longer produced by the open-vocabulary pipeline.
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
    """Open-vocabulary mixture distribution over architectural styles.

    Models style as a continuous mixture instead of a single label. Keys of
    ``distribution`` are open-vocabulary style names (any non-empty string —
    typically a KB candidate name); empty keys are dropped, negatives clipped
    to 0, and remaining values normalised to sum=1.0. ``primary`` is the argmax
    style. ``secondary`` lists every style with probability ≥ 0.15, ranked by
    descending probability (excluding primary). Contract used by the
    advocate / arbiter agent outputs.
    """

    distribution: Dict[str, float]
    primary: str
    secondary: List[str]

    @field_validator("distribution")
    @classmethod
    def normalise_distribution(cls, v: Dict[str, float]) -> Dict[str, float]:
        """Drop empty keys, clip negatives, renormalise to sum=1.0."""
        cleaned = {
            k: max(0.0, val)
            for k, val in v.items()
            if isinstance(k, str) and k.strip()
        }
        total = sum(cleaned.values())
        if total <= 0:
            raise ValueError(
                "StyleDistribution must contain at least one style with positive probability"
            )
        return {k: val / total for k, val in cleaned.items()}

    @field_validator("primary")
    @classmethod
    def primary_not_empty(cls, v: str) -> str:
        """Ensure primary is a non-empty style name."""
        if not v or not v.strip():
            raise ValueError("primary must be a non-empty style name")
        return v


# ── Open-vocabulary: Knowledge Base + Evidence Sheet ─────────────────────────

class StyleEntry(BaseModel):
    """One architectural style in the open-vocabulary knowledge base.

    Loaded from ``chatbot/knowledge/styles.json``. Adding a style = appending
    one entry (no model retraining). Provenance fields trace each entry to
    authoritative sources (Getty AAT / Wikidata / reference texts).
    """

    id: str
    name: str
    aliases: List[str] = Field(default_factory=list)
    parent: Optional[str] = None
    region: List[str] = Field(default_factory=list)
    period: str = ""
    defining_features: List[str] = Field(default_factory=list)
    expected_profile: Dict[str, str] = Field(default_factory=dict)
    description: str = ""
    aat_id: Optional[str] = None
    wikidata_id: Optional[str] = None
    references: List[str] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    """One piece of visual evidence extracted by the VLM (Agent A).

    ``dimension`` is one evidence-sheet dimension (e.g. "roof", "arch",
    "ornament"). ``feature`` is the observed value, ideally from the controlled
    feature lexicon. ``suggested_styles`` are the open-vocabulary style names
    this evidence points to (free text, matched to the KB downstream).

    NO ``confidence`` field by design: an LLM's self-reported confidence is
    unreliable (it may emit an arbitrary number). NO bounding box either: VLM
    pixel coordinates vary run-to-run and across providers, do not affect the
    style decision, and only add noise to the judge prompt. Uncertainty is
    measured instead from inter-judge agreement + sampling variance downstream.
    """

    dimension: str
    feature: str
    suggested_styles: List[str] = Field(default_factory=list)
    note: str = ""


class EvidenceSheet(BaseModel):
    """Structured multi-dimensional evidence extracted from one image (Agent A).

    Replaces YOLO components + ResNet style_prior as the single evidence source
    for the open-vocabulary pipeline. ``items`` are the localized observations;
    ``proposed_styles`` aggregates every open-vocabulary style name the VLM
    suggested (deduped); ``overall_note`` is a free-text holistic impression.
    """

    items: List[EvidenceItem] = Field(default_factory=list)
    proposed_styles: List[str] = Field(default_factory=list)
    # Building-level FAMILY guesses from Agent A (e.g. "Islamic", "East Asian").
    # Coarser than a style name and easier to get right; the orchestrator expands
    # each into its KB family members so the correct child style is guaranteed to
    # be a candidate (Phase 1a coarse-to-fine). Empty for sheets predating this.
    proposed_families: List[str] = Field(default_factory=list)
    overall_note: str = ""


# ── Pipeline contract (open-vocabulary) ───────────────────────────────────────

class PipelineInput(BaseModel):
    """Input to the open-vocabulary pipeline runner.

    Produced by the orchestrator after Stage A (Agent A evidence extraction)
    and Stage B (KB grounding):
    - ``evidence_sheet``: structured 12-dimension evidence + proposed styles.
    - ``candidate_names``: the KB-grounded candidate style names (top-K) the
      advocate/arbiter are allowed to score.
    - ``candidate_kb_text``: rendered KB descriptions of those candidates,
      injected into the prompts.
    - ``full_image_base64``: whole building image (base64 JPEG) so the arbiter
      always has visual context.
    """

    evidence_sheet: Optional[EvidenceSheet] = None
    candidate_names: List[str] = Field(default_factory=list)
    candidate_kb_text: str = ""
    full_image_base64: Optional[str] = None
    # Stage B signal: mean pairwise Jaccard of the proposed KB-id sets across the
    # extraction calls (None when < 2 resolvable). Low → the calls disagreed →
    # multi-style/hybrid image. Threads into the runner's ``hybrid`` decision.
    extraction_agreement: Optional[float] = None
    # Fraction of Stage A extraction calls that succeeded (surviving sheets /
    # attempted calls). < 1.0 means provider failures degraded the evidence;
    # feeds the run-quality confidence penalty.
    extraction_completeness: float = 1.0
    # Ranked style names from the independent "free read" (a strong vision model
    # naming the style directly from the image, with no candidate/sheet
    # constraint). Surfaced to the arbiter as a decorrelated opinion. Empty when
    # the free read is disabled or failed.
    free_read_styles: List[str] = Field(default_factory=list)
    # Subset of ``candidate_names`` that are NOT in the curated KB (open-set
    # escape, gated by OUT_OF_KB_*). They flow through the panel like any
    # candidate but carry a "proposed / pending review" tag and must clear a
    # higher agreement bar to be displayed. Empty when the feature is off.
    out_of_kb_names: List[str] = Field(default_factory=list)


# ── Per-component agent outputs ────────────────────────────────────────────────

class Agent1Output(BaseModel):
    """Agent 1 (Gemini vision): geometric feature description of one component."""

    component_id: str
    feature_description: str


class Agent2Output(BaseModel):
    """Legacy per-component style distribution (retained for shape compatibility).

    style_distribution keys are style names, values sum to ~1.0. Not produced by
    the open-vocabulary pipeline.
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


class PanelVerdict(BaseModel):
    """One independent judge's verdict in the consensus panel (Stage C).

    Each judge (Gemini / DeepSeek / OpenAI) scores the KB candidates into a
    mixture from the SAME evidence sheet, without seeing the other judges'
    output. ``style_distribution`` is None and ``failed`` True when that judge's
    LLM call or JSON parse failed — such a verdict is excluded from the
    inter-judge agreement computation.
    """

    judge: str
    model_id: str
    style_distribution: Optional[StyleDistribution] = None
    reasoning: str = ""
    failed: bool = False


class AgentRunRecord(BaseModel):
    """Telemetry for a single LLM agent invocation during one analysis.

    Collected by the pipeline and persisted to the ``AgentRuns`` table so the
    admin UI can show real per-agent run counts, success rates, and latency.
    """

    agent_name: str
    model_id: str
    latency_ms: int
    parse_success: bool
    # Debug telemetry (persisted to AgentRuns.RawOutput / ParsedOutput / OutputData
    # so a run can be audited — fixes the all-NULL AgentRuns from the 503 debug).
    raw_output: Optional[str] = None
    parsed_output: Optional[str] = None
    error: Optional[str] = None


class FinalAnalysisResult(BaseModel):
    """Final output of the open-vocabulary pipeline, returned to the API router.

    Single-label fields (``style``, ``confidence``, ``explanation``,
    ``key_evidence``) mirror the primary of the mixture for DB persistence and
    simple clients. Mixture fields:

    - ``style_distribution``: open-vocabulary mixture from the arbiter (Agent 7)
    - ``composition_explanation``: narrative describing the mix (e.g.
      "Dominant Gothic with a Romanesque undertone because…")
    - ``evidence_per_style``: per-style supporting bullets, one list per style
      in the mixture
    - ``gradcam_b64``: unused in the open-vocabulary pipeline (always None)

    ``style`` mirrors ``style_distribution.primary`` and ``confidence`` mirrors
    its probability mass (reported alongside ``certainty_margin`` /
    ``distribution_entropy`` because a single probability is not, on its own,
    a reliable confidence).
    """

    style: str
    confidence: float
    explanation: str
    key_evidence: List[str]
    # Empty in the open-vocabulary pipeline (no per-component YOLO stage); kept
    # for response/DB shape compatibility.
    components: List[ComponentAnalysis] = Field(default_factory=list)
    # Stage C/D: the independent judges' verdicts and their mean pairwise
    # Spearman agreement (None when it cannot be defined — < 2 valid judges).
    # ``panel_agreement`` is the PRIMARY uncertainty signal (decision #73/#75).
    panel_verdicts: List[PanelVerdict] = Field(default_factory=list)
    panel_agreement: Optional[float] = None
    processing_time_ms: float
    style_distribution: Optional[StyleDistribution] = None
    composition_explanation: Optional[str] = None
    evidence_per_style: Optional[Dict[str, List[str]]] = None
    gradcam_b64: Optional[str] = None
    # Stage A evidence: the merged 12-dimension evidence sheet (Agent A) so the
    # client can show the concrete observed features per dimension, not just the
    # prose narrative. None for legacy analyses that predate this field.
    evidence_sheet: Optional[EvidenceSheet] = None
    # Vietnamese version of the evidence sheet (feature/note translated; dimension
    # + suggested_styles preserved). None when bilingual is off / translation
    # failed → the frontend falls back to the English ``evidence_sheet``.
    evidence_sheet_vi: Optional[EvidenceSheet] = None
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
    # Overall run health (A4b): "completed" (all judges + extraction calls
    # succeeded, primary arbiter answered), "degraded" (some judge/extraction
    # lost, or the arbiter fell back to a backup provider / the panel average),
    # or "failed" (no judge produced a usable verdict). Persisted inside
    # DetailJson; the AnalysisStatus DB column keeps its documented vocabulary.
    run_status: str = "completed"
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
    # Hybrid (multi-style) determination — SEPARATE from ``uncertain``. True when
    # the final mixture has ≥ 2 significant styles OR the extraction calls
    # disagreed (low ``extraction_agreement``). A hybrid is a confident,
    # fully-explained mixture answer (see ``evidence_per_style``), NOT a refusal.
    hybrid: bool = False
    # Mean pairwise Jaccard of the proposed KB-id sets across extraction calls
    # (None when < 2 resolvable). Reported for transparency; drives ``hybrid``.
    extraction_agreement: Optional[float] = None
    # Stage B output: the KB-grounded candidate style names (top-K) the panel +
    # arbiter were allowed to score. Exposed so evaluation can measure candidate
    # recall (is the ground-truth style even in this set?) separately from the
    # judging accuracy. Empty for legacy analyses that predate this field.
    candidate_names: List[str] = Field(default_factory=list)
    # Styles in the final mixture that are NOT in the curated KB (open-set escape).
    # Non-empty only when OUT_OF_KB_ENABLED and such a style cleared the higher
    # agreement bar to be displayed. The client badges these "outside catalog —
    # pending review"; they are also (re)queued in the KB suggestion store.
    out_of_kb_styles: List[str] = Field(default_factory=list)
    # Per-agent telemetry for this analysis (Agent 1..7 LLM calls). Additive and
    # excluded from the API response; consumed by the router to write AgentRuns.
    agent_runs: List[AgentRunRecord] = []

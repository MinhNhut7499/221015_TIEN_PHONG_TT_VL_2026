"""Tests for P3 (confidence noise reduction) + P4 (YOLO/CNN cross-check).

Covers:
- material stream gating in prompts (mock material withheld)
- _normalize_votes / _distribution_stats helpers
- check_prior_vote_agreement
- pipeline integration: dual certainty metrics + 0-component fallback
"""
import base64
import io

import pytest
from PIL import Image

from chatbot.services.mock_global_feature_service import MockGlobalFeatureService
from chatbot.services.mock_material_classifier import MockMaterialClassifierService
from chatbot.services.pipeline_runner import (
    PipelineRunner,
    _distribution_stats,
    _normalize_votes,
)
from chatbot.utils.fusion import numeric_fuse
from chatbot.utils.prompt_builder import build_agent5_prompt
from chatbot.utils.rule_checker import check_prior_vote_agreement, compute_attribute_affinity
from chatbot.utils.schemas import (
    AttributeVector,
    MaterialDistribution,
    PipelineInput,
    STYLE_CLASSES,
)
from test.test_pipeline_integration import (
    _StubFinalLLM,
    _StubTextLLM,
    _StubVisionLLM,
    _make_image_bytes,
)


def _material() -> MaterialDistribution:
    return MaterialDistribution(
        distribution={"stone": 0.6, "concrete": 0.2, "glass": 0.1, "brick": 0.05, "metal": 0.05},
        dominant="stone",
        confidence=0.6,
    )


# ── P3: material stream gating ──────────────────────────────────────────────────

def test_agent5_prompt_hides_mock_material() -> None:
    """When material is unavailable, the material stream is withheld."""
    prompt = build_agent5_prompt(
        {"Gothic": 0.9}, ["arch → Gothic"], _material(), material_available=False
    )
    assert "unavailable" in prompt.lower()
    assert "dominant=stone" not in prompt


def test_agent5_prompt_shows_real_material() -> None:
    """When material is available, the dominant material is presented."""
    prompt = build_agent5_prompt(
        {"Gothic": 0.9}, ["arch → Gothic"], _material(), material_available=True
    )
    assert "dominant=stone" in prompt


# ── P3: helpers ────────────────────────────────────────────────────────────────

def test_normalize_votes_sums_to_one() -> None:
    out = _normalize_votes({"Gothic": 1.2, "Baroque": 0.6, "Modernism": 0.2})
    assert abs(sum(out.values()) - 1.0) < 1e-9
    assert max(out, key=out.get) == "Gothic"


def test_normalize_votes_all_zero_passthrough() -> None:
    out = _normalize_votes({"Gothic": 0.0, "Baroque": 0.0})
    assert sum(out.values()) == 0.0


def test_distribution_stats_one_hot() -> None:
    margin, entropy = _distribution_stats({"Gothic": 1.0})
    assert margin == 1.0
    assert entropy == 0.0


def test_distribution_stats_spread_is_less_certain() -> None:
    margin, entropy = _distribution_stats({"Gothic": 0.4, "Baroque": 0.35, "Modernism": 0.25})
    assert 0.0 < margin < 0.1
    assert entropy > 0.5


# ── P4: cross-check ─────────────────────────────────────────────────────────────

def test_prior_vote_agreement_flags_disagreement() -> None:
    note = check_prior_vote_agreement(
        {"Gothic": 0.7, "Baroque": 0.3},
        {"Modernism": 0.6, "Gothic": 0.2, "Baroque": 0.2},
    )
    assert note is not None
    assert "Gothic" in note and "Modernism" in note


def test_prior_vote_agreement_silent_when_agree() -> None:
    note = check_prior_vote_agreement(
        {"Gothic": 0.7, "Baroque": 0.3}, {"Gothic": 0.6, "Baroque": 0.4}
    )
    assert note is None


def test_prior_vote_agreement_silent_when_no_votes() -> None:
    assert check_prior_vote_agreement({"Gothic": 0.0}, {"Gothic": 0.9}) is None


# ── Integration: dual metrics + 0-component fallback ────────────────────────────

async def _full_pipeline_input(components: list) -> PipelineInput:
    image_bytes = _make_image_bytes()
    material = await MockMaterialClassifierService().classify(image_bytes)
    global_features = await MockGlobalFeatureService().extract(image_bytes)
    img = Image.new("RGB", (32, 32), color=(150, 100, 80))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    full_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return PipelineInput(
        components=components,
        material=material,
        global_features=global_features,
        material_available=False,
        full_image_base64=full_b64,
    )


@pytest.mark.asyncio
async def test_pipeline_reports_dual_certainty_metrics() -> None:
    """FinalAnalysisResult carries certainty_margin + distribution_entropy."""
    runner = PipelineRunner(_StubVisionLLM(), _StubTextLLM(), _StubFinalLLM())
    from test.test_pipeline_integration import _build_pipeline_input

    result = await runner.run(await _build_pipeline_input())
    assert result.certainty_margin is not None and result.certainty_margin > 0
    assert result.distribution_entropy is not None and result.distribution_entropy > 0


@pytest.mark.asyncio
async def test_pipeline_zero_components_falls_back_gracefully() -> None:
    """No components → pipeline still produces a verdict from the global streams."""
    runner = PipelineRunner(_StubVisionLLM(), _StubTextLLM(), _StubFinalLLM())
    result = await runner.run(await _full_pipeline_input([]))
    assert result.style in STYLE_CLASSES
    assert result.degraded is True
    assert any("no components" in w.lower() for w in result.warnings)
    assert result.components == []


# ── A: standardised attribute affinity separates Gothic vs Art Nouveau ──────────

def test_attribute_affinity_favours_art_nouveau_on_organic_cues() -> None:
    """A 'tall + ornate BUT organic/asymmetric' building should lean Art Nouveau,
    not Gothic — the bug we are fixing (verticality no longer dominates)."""
    observed = AttributeVector(
        symmetry_score=0.42,          # asymmetric → Art Nouveau
        vertical_dominance=0.80,      # tall → looks Gothic
        horizontal_dominance=0.45,
        curvature_score=0.78,         # organic curves → Art Nouveau
        surface_roughness=0.55,
        edge_density=0.70,            # ornate (shared)
        edge_orientation_entropy=2.60,  # organic ornament → Art Nouveau
    )
    aff = compute_attribute_affinity(observed)
    assert aff["Art Nouveau"] > aff["Gothic"]


# ── B: numeric_fuse weighting + missing-stream redistribution ───────────────────

def test_numeric_fuse_attribute_cannot_override_strong_agreement() -> None:
    """votes + prior both back Gothic; small attribute weight for Art Nouveau
    must not flip the result."""
    votes = {"Gothic": 0.8, "Art Nouveau": 0.2}
    prior = {"Gothic": 0.75, "Art Nouveau": 0.25}
    affinity = {"Art Nouveau": 1.0, "Gothic": 0.0}
    fused = numeric_fuse(votes, prior, affinity,
                         weight_votes=0.45, weight_prior=0.45, weight_attribute=0.10)
    assert abs(sum(fused.values()) - 1.0) < 1e-9
    assert max(fused, key=fused.get) == "Gothic"


def test_numeric_fuse_redistributes_when_stream_missing() -> None:
    """A missing stream (None) must not shrink total mass below 1.0."""
    fused = numeric_fuse(None, {"Gothic": 0.6, "Baroque": 0.4}, None,
                         weight_votes=0.45, weight_prior=0.45, weight_attribute=0.10)
    assert abs(sum(fused.values()) - 1.0) < 1e-9
    assert max(fused, key=fused.get) == "Gothic"


# ── B: Tier-2 LLM failure → numeric fallback (no 500) ───────────────────────────

@pytest.mark.asyncio
async def test_pipeline_falls_back_to_numeric_when_llm_fusion_fails() -> None:
    """If Agent 7 raises, the pipeline returns a numeric-fusion verdict (degraded)."""

    class _BrokenFinal(_StubFinalLLM):
        async def chat_structured(self, prompt, image_base64=None):
            raise RuntimeError("503 model overloaded")

    from test.test_pipeline_integration import _build_pipeline_input

    runner = PipelineRunner(_StubVisionLLM(), _StubTextLLM(), _BrokenFinal())
    result = await runner.run(await _build_pipeline_input())
    assert result.style in STYLE_CLASSES
    assert result.degraded is True
    assert any("numeric fusion" in w.lower() for w in result.warnings)


# ── C: abstention on a near-tie ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pipeline_flags_uncertain_on_near_tie() -> None:
    """A near-tie final distribution → uncertain=True + top-K candidates."""

    import json as _json

    class _TieFinal(_StubFinalLLM):
        async def chat_structured(self, prompt, image_base64=None):
            payload = {
                "style_distribution": {"Gothic": 0.34, "Renaissance": 0.33, "Baroque": 0.33},
                "composition_explanation": "near tie",
                "evidence_per_style": {
                    "Gothic": ["a", "b"], "Renaissance": ["a", "b"], "Baroque": ["a", "b"],
                },
            }
            return "```json\n" + _json.dumps(payload) + "\n```"

    from test.test_pipeline_integration import _build_pipeline_input

    runner = PipelineRunner(_StubVisionLLM(), _StubTextLLM(), _TieFinal())
    result = await runner.run(await _build_pipeline_input())
    assert result.uncertain is True
    assert len(result.candidates) == 3
    assert result.candidates[0].probability >= result.candidates[1].probability


# ── G: learned-fuser feature vector (single source of truth) ────────────────────

def test_build_fuser_features_shape_and_material_gating() -> None:
    from chatbot.services.fuser_service import (
        FEATURE_DIM,
        FLAG_INDEX,
        MATERIAL_SLICE,
        build_fuser_features,
    )

    attrs = AttributeVector(
        symmetry_score=0.5, vertical_dominance=0.5, horizontal_dominance=0.5,
        curvature_score=0.5, surface_roughness=0.5, edge_density=0.5,
        edge_orientation_entropy=1.0,
    )
    prior = {s: 1.0 / len(STYLE_CLASSES) for s in STYLE_CLASSES}

    # Material unavailable → material block zeroed + flag 0.
    feat = build_fuser_features(prior, attrs, [], None, material_available=False)
    assert feat.shape == (FEATURE_DIM,)
    assert feat[MATERIAL_SLICE].sum() == 0.0
    assert feat[FLAG_INDEX] == 0.0

    # Material available → material block carries the distribution + flag 1.
    feat2 = build_fuser_features(prior, attrs, [], _material(), material_available=True)
    assert abs(feat2[MATERIAL_SLICE].sum() - 1.0) < 1e-6
    assert feat2[FLAG_INDEX] == 1.0

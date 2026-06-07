"""Integration test for PipelineRunner with stub LLM services.

Wires PipelineRunner to in-memory stub Gemini / DeepSeek / OpenAI services
that return prescribed JSON for each agent call. Verifies the FULL flow
end-to-end and asserts that the mixture-mode fields on FinalAnalysisResult
are populated alongside the legacy single-label fields.

No real LLM calls, no GPU, no DB.

Run with:
    pytest test/test_pipeline_integration.py -v
"""
import asyncio
import base64
import io
import json
from typing import Optional

import pytest
from PIL import Image

from chatbot.services.mock_global_feature_service import MockGlobalFeatureService
from chatbot.services.mock_material_classifier import MockMaterialClassifierService
from chatbot.services.pipeline_runner import PipelineRunner
from chatbot.utils.schemas import (
    BoundingBox,
    DetectedComponent,
    PipelineInput,
    STYLE_CLASSES,
)


# ── Test image helpers ────────────────────────────────────────────────────────

def _make_jpeg_b64() -> str:
    """Tiny JPEG encoded as base64 — used as both crop and full_image."""
    img = Image.new("RGB", (32, 32), color=(150, 100, 80))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _make_image_bytes() -> bytes:
    """Tiny JPEG bytes — fed into MockGlobalFeatureService for real CV attributes."""
    img = Image.new("RGB", (256, 256), color=(120, 100, 90))
    pixels = img.load()
    # Add some structure so attributes are non-trivial
    for x in range(256):
        for y in range(256):
            if x % 32 < 16:
                pixels[x, y] = (200, 180, 160)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


# ── Stub LLM services ─────────────────────────────────────────────────────────

class _StubVisionLLM:
    """Stand-in for GeminiService used by Agent 1 + Agent 2.

    Routes by prompt content:
    - prompts asking for geometric description → return ``agent1_text``
    - everything else (Agent 2) → return JSON style distribution
    """

    def __init__(self) -> None:
        self.agent1_text = (
            "Tall, pointed arch with vertical mullions and stone surround."
        )
        self.agent2_distribution = {
            "Gothic": 0.65,
            "Renaissance": 0.20,
            "Baroque": 0.10,
            "Neoclassical": 0.05,
        }
        self.calls: list[str] = []

    async def generate_with_image(
        self, prompt: str, image_base64: str, temperature: float
    ) -> str:
        self.calls.append(prompt[:60])
        if "Describe the GEOMETRIC" in prompt:
            return self.agent1_text
        # Agent 2 — emit JSON distribution
        return json.dumps(self.agent2_distribution)


class _StubTextLLM:
    """Stand-in for DeepSeekService used by Agents 3b, 4, 5, 6.

    Routes by prompt content. Agent 4 emits ``style_distribution`` (mixture
    mode); Agent 5 emits ``style_distribution + composition_narrative``;
    Agent 6 emits legacy single-label adversary. Agent 3b is not exercised
    here because none of the test components trigger contradictions.
    """

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def chat(self, prompt: str, temperature: float = 0.5) -> str:
        self.calls.append(prompt[:60])
        if "ONE component of a building" in prompt:
            # Agent 4 — per-component mixture
            return json.dumps(
                {
                    "style_distribution": {
                        "Gothic": 0.7,
                        "Renaissance": 0.2,
                        "Baroque": 0.1,
                    },
                    "reasoning": "Pointed arch with stone surround → Gothic",
                }
            )
        if "EVIDENCE STREAM 1" in prompt and "Composition narrative" not in prompt:
            # Agent 5 — primary advocate emits mixture + narrative
            return json.dumps(
                {
                    "style_distribution": {
                        "Gothic": 0.6,
                        "Renaissance": 0.25,
                        "Baroque": 0.15,
                    },
                    "composition_narrative": (
                        "Dominant Gothic with Renaissance influence; "
                        "vertical proportions and pointed arch dominate, "
                        "but symmetric stone facade hints at classical revival."
                    ),
                }
            )
        if "Another analyst concluded" in prompt:
            # Agent 6 — alternative single-label adversary
            return json.dumps(
                {
                    "style": "Renaissance",
                    "confidence": 0.45,
                    "reasoning": "Symmetric stone facade with classical proportions.",
                }
            )
        # Fallback (e.g. Agent 3b if a contradiction were triggered)
        return json.dumps(
            {"has_contradiction": False, "contradiction_analysis": "", "violated_rules": []}
        )


class _StubFinalLLM:
    """Stand-in for OpenAIService used by Agent 7.

    Wraps the final mixture verdict in a fenced ```json block so the real
    ``OpenAIService.extract_json`` regex extracts it correctly.
    """

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.last_prompt: Optional[str] = None

    async def chat_structured(
        self, prompt: str, image_base64: Optional[str] = None
    ) -> str:
        self.calls.append(prompt[:60])
        self.last_prompt = prompt
        payload = {
            "style_distribution": {
                "Gothic": 0.55,
                "Renaissance": 0.28,
                "Baroque": 0.17,
            },
            "composition_explanation": (
                "Predominantly Gothic with secondary Renaissance and minor "
                "Baroque influence due to mixed massing and ornament cues."
            ),
            "evidence_per_style": {
                "Gothic": [
                    "pointed_arch detected with high confidence",
                    "vertical_dominance dominates whole-image attributes",
                ],
                "Renaissance": [
                    "stone material consistent with classical revival",
                    "moderate symmetry suggests classical influence",
                ],
                "Baroque": ["curvature score non-zero from facade molding"],
            },
        }
        return "Reasoning ...\n```json\n" + json.dumps(payload) + "\n```\n"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _build_stub_runner() -> PipelineRunner:
    """PipelineRunner wired to the three default stub LLM services."""
    return PipelineRunner(_StubVisionLLM(), _StubTextLLM(), _StubFinalLLM())


async def _build_pipeline_input() -> PipelineInput:
    """Single-component PipelineInput with real mock material + global features."""
    crop_b64 = _make_jpeg_b64()
    component = DetectedComponent(
        component_id="test-comp-001",
        component_type="arch",
        detection_confidence=0.85,
        bounding_box=BoundingBox(x_min=0, y_min=0, x_max=100, y_max=200),
        crop_base64=crop_b64,
        full_image_base64=crop_b64,
    )
    image_bytes = _make_image_bytes()
    material = await MockMaterialClassifierService().classify(image_bytes)
    global_features = await MockGlobalFeatureService().extract(image_bytes)
    return PipelineInput(
        components=[component],
        material=material,
        global_features=global_features,
    )


# ── End-to-end test ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pipeline_runs_end_to_end_with_mixture_output() -> None:
    """Full pipeline returns mixture + legacy fields populated and consistent."""
    stub_runner = _build_stub_runner()
    pipeline_input = await _build_pipeline_input()
    result = await stub_runner.run(pipeline_input)

    # Legacy fields
    assert result.style == "Gothic"
    assert 0.0 < result.confidence <= 1.0
    assert isinstance(result.explanation, str) and result.explanation
    assert isinstance(result.key_evidence, list) and result.key_evidence

    # Mixture fields
    assert result.style_distribution is not None
    dist = result.style_distribution.distribution
    assert set(dist.keys()).issubset(set(STYLE_CLASSES))
    assert abs(sum(dist.values()) - 1.0) < 1e-6
    assert result.style_distribution.primary == "Gothic"
    # Renaissance (0.28) crosses 0.15 threshold; Baroque (0.17) crosses too.
    assert set(result.style_distribution.secondary) == {"Renaissance", "Baroque"}

    # Legacy mirrors primary
    assert result.style == result.style_distribution.primary
    assert abs(result.confidence - dist[result.style_distribution.primary]) < 1e-6

    # composition_explanation populated; evidence_per_style covers every mixture style
    assert result.composition_explanation
    assert result.evidence_per_style is not None
    for style in result.style_distribution.distribution:
        assert style in result.evidence_per_style
        assert len(result.evidence_per_style[style]) >= 1

    # gradcam_b64 forwarded from MockGlobalFeatureService (None in mock)
    assert result.gradcam_b64 is None

    # Tier 1 component analysis preserved
    assert len(result.components) == 1
    ca = result.components[0]
    assert ca.agent4.style_distribution is not None
    assert ca.agent4.style_distribution.primary in STYLE_CLASSES
    # Agent4 legacy mirrors primary too
    assert ca.agent4.style == ca.agent4.style_distribution.primary

    # Agent 5 received mixture; Agent 6 stays single-label by design
    # (Agent6Output has no style_distribution field — adversarial role unchanged)
    assert result.agent5.style_distribution is not None
    assert result.agent5.composition_narrative
    assert isinstance(result.agent6.style, str) and result.agent6.style
    assert not hasattr(result.agent6, "style_distribution") or \
        getattr(result.agent6, "style_distribution", None) is None


@pytest.mark.asyncio
async def test_pipeline_evidence_backfill_when_llm_omits_a_style() -> None:
    """If Agent 7 omits evidence for one mixture style, runner back-fills a placeholder."""

    class _PartialEvidenceFinal(_StubFinalLLM):
        async def chat_structured(
            self, prompt: str, image_base64: Optional[str] = None
        ) -> str:
            payload = {
                "style_distribution": {"Gothic": 0.7, "Renaissance": 0.3},
                "composition_explanation": "Test partial evidence backfill.",
                # Intentionally omit Renaissance entry
                "evidence_per_style": {
                    "Gothic": ["pointed_arch", "vertical_dominance high"]
                },
            }
            return "```json\n" + json.dumps(payload) + "\n```"

    pipeline_input = await _build_pipeline_input()
    runner = PipelineRunner(_StubVisionLLM(), _StubTextLLM(), _PartialEvidenceFinal())
    result = await runner.run(pipeline_input)

    assert result.evidence_per_style is not None
    assert "Gothic" in result.evidence_per_style
    assert "Renaissance" in result.evidence_per_style
    # Renaissance was back-filled with a placeholder bullet
    assert any(
        "no specific evidence" in b.lower()
        for b in result.evidence_per_style["Renaissance"]
    )


@pytest.mark.asyncio
async def test_pipeline_handles_legacy_llm_output_shape() -> None:
    """If a stub LLM returns the OLD ``{style, confidence}`` schema for Agent 5/7,
    the runner still produces a valid StyleDistribution via 1-hot fallback."""

    class _LegacyText(_StubTextLLM):
        async def chat(self, prompt: str, temperature: float = 0.5) -> str:
            if "EVIDENCE STREAM 1" in prompt and "Composition narrative" not in prompt:
                return json.dumps(
                    {
                        "style": "Baroque",
                        "confidence": 0.82,
                        "reasoning": "Legacy single-label output.",
                    }
                )
            return await super().chat(prompt, temperature)

    class _LegacyFinal(_StubFinalLLM):
        async def chat_structured(
            self, prompt: str, image_base64: Optional[str] = None
        ) -> str:
            return "```json\n" + json.dumps(
                {
                    "style": "Baroque",
                    "confidence": 0.91,
                    "explanation": "Legacy single-label final.",
                    "key_evidence": ["legacy bullet A", "legacy bullet B"],
                }
            ) + "\n```"

    pipeline_input = await _build_pipeline_input()
    runner = PipelineRunner(_StubVisionLLM(), _LegacyText(), _LegacyFinal())
    result = await runner.run(pipeline_input)

    assert result.style == "Baroque"
    assert result.style_distribution is not None
    assert result.style_distribution.primary == "Baroque"
    # 1-hot fallback → single-entry distribution
    assert result.style_distribution.distribution == {"Baroque": 1.0}
    assert result.style_distribution.secondary == []
    # Legacy key_evidence preserved
    assert "legacy bullet A" in result.key_evidence


@pytest.mark.asyncio
async def test_pipeline_forwards_bounding_box_to_component_analysis() -> None:
    """The YOLO bounding_box must survive into ComponentAnalysis (for UI overlay)."""
    stub_runner = _build_stub_runner()
    pipeline_input = await _build_pipeline_input()
    result = await stub_runner.run(pipeline_input)

    assert len(result.components) == 1
    bbox = result.components[0].bounding_box
    assert bbox is not None
    assert (bbox.x_min, bbox.y_min, bbox.x_max, bbox.y_max) == (0, 0, 100, 200)


@pytest.mark.asyncio
async def test_pipeline_bilingual_translation_populates_vi_fields() -> None:
    """When the text LLM returns a translation, *_vi fields are populated."""

    class _TranslatingText(_StubTextLLM):
        async def chat(self, prompt: str, temperature: float = 0.5) -> str:
            if "into natural" in prompt and "Vietnamese" in prompt:
                return "```json\n" + json.dumps(
                    {
                        "explanation": "Chủ yếu là Gothic với ảnh hưởng Phục Hưng.",
                        "key_evidence": ["vòm nhọn", "tỷ lệ theo chiều dọc"],
                        "composition_explanation": "Gothic trội, pha Phục Hưng.",
                        "evidence_per_style": {"Gothic": ["vòm nhọn"]},
                    }
                ) + "\n```"
            return await super().chat(prompt, temperature)

    pipeline_input = await _build_pipeline_input()
    runner = PipelineRunner(_StubVisionLLM(), _TranslatingText(), _StubFinalLLM())
    result = await runner.run(pipeline_input)

    assert result.explanation_vi == "Chủ yếu là Gothic với ảnh hưởng Phục Hưng."
    assert result.key_evidence_vi == ["vòm nhọn", "tỷ lệ theo chiều dọc"]
    assert result.composition_explanation_vi == "Gothic trội, pha Phục Hưng."
    assert result.evidence_per_style_vi == {"Gothic": ["vòm nhọn"]}


# ── Graceful degradation (P2) ───────────────────────────────────────────────────

class _AllFailVision(_StubVisionLLM):
    """Vision LLM that always raises — fails Agent 1, dropping the component."""

    async def generate_with_image(
        self, prompt: str, image_base64: str, temperature: float
    ) -> str:
        raise RuntimeError("503 model overloaded")


class _Agent2FailVision(_StubVisionLLM):
    """Agent 1 succeeds; every Agent 2 call raises → Agent 2 fully degraded."""

    async def generate_with_image(
        self, prompt: str, image_base64: str, temperature: float
    ) -> str:
        if "Describe the GEOMETRIC" in prompt:
            return self.agent1_text
        raise RuntimeError("503 model overloaded")


@pytest.mark.asyncio
async def test_pipeline_drops_failed_component_and_flags_degraded() -> None:
    """A component whose Agent 1 fails is dropped; the request still succeeds."""
    pipeline_input = await _build_pipeline_input()
    runner = PipelineRunner(_AllFailVision(), _StubTextLLM(), _StubFinalLLM())
    result = await runner.run(pipeline_input)

    # Pipeline degraded but did NOT crash — Tier 2 still ran on global evidence.
    assert result.degraded is True
    assert result.warnings
    assert any("dropped" in w.lower() for w in result.warnings)
    assert len(result.components) == 0
    assert result.style in STYLE_CLASSES


@pytest.mark.asyncio
async def test_agent2_degraded_excluded_from_votes() -> None:
    """When Agent 2 fully fails, its component is kept but excluded from votes."""
    from chatbot.services.pipeline_runner import compute_aggregated_votes

    pipeline_input = await _build_pipeline_input()
    runner = PipelineRunner(_Agent2FailVision(), _StubTextLLM(), _StubFinalLLM())
    result = await runner.run(pipeline_input)

    assert result.degraded is True
    assert any("agent 2 degraded" in w.lower() for w in result.warnings)
    # Component survives (Agent 1 succeeded) but is flagged degraded.
    assert len(result.components) == 1
    assert result.components[0].agent2.degraded is True
    # Its placeholder uniform must NOT pollute the vote table.
    votes = compute_aggregated_votes(result.components)
    assert sum(votes.values()) == 0.0

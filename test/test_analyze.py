"""Test suite for the analysis pipeline endpoints and core utilities.

Run with: pytest test/ -v

Groups:
- Auth guards            : no token → 403 on both endpoints
- 404 handling           : unknown file_id → 404
- 503 handling           : LLM not configured → 503
- History stub           : authenticated user → 200 empty list
- MockYOLOService        : same bytes → same components (deterministic)
- MockMaterialClassifier : same bytes → same material distribution (deterministic)
- compute_votes          : weighted aggregation produces correct sums
- check_rules            : exclusive component vs incompatible style → contradiction
- check_material         : material vs style compatibility lookup
"""
import io

import pytest
from PIL import Image
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.security.security import create_access_token
from chatbot.services.mock_global_feature_service import MockGlobalFeatureService
from chatbot.services.mock_material_classifier import MockMaterialClassifierService
from chatbot.services.mock_yolo_service import MockYOLOService
from chatbot.services.pipeline_runner import (
    _build_style_distribution_safe,
    compute_aggregated_votes,
)
from chatbot.utils.rule_checker import check_material_consistency, check_rules
from chatbot.utils.schemas import (
    Agent1Output,
    Agent2Output,
    Agent3Output,
    Agent4Output,
    AttributeVector,
    ComponentAnalysis,
    GlobalFeatureOutput,
    MATERIAL_CLASSES,
    STYLE_CLASSES,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def user_token() -> str:
    """Valid JWT for a regular user."""
    return create_access_token({"sub": "user-uid-001", "email": "user@test.com", "role": "user"})


def _make_jpeg(width: int = 10, height: int = 10, color: tuple = (100, 150, 200)) -> bytes:
    """Create a minimal valid JPEG image using Pillow."""
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


_MINIMAL_IMAGE = _make_jpeg(color=(100, 150, 200))
_OTHER_IMAGE = _make_jpeg(color=(200, 100, 50))


# ── Auth guard tests ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_analyze_no_token_returns_403() -> None:
    """POST /analyze without token should return 403."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/analyze/", json={"file_id": "some-id"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_history_no_token_returns_403() -> None:
    """GET /analyze/history without token should return 403."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/analyze/history")
    assert response.status_code == 403


# ── 404 / 503 handling ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_analyze_unknown_file_id_returns_404(user_token: str) -> None:
    """POST /analyze with a non-existent file_id should return 404."""
    headers = {"Authorization": f"Bearer {user_token}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/analyze/",
            json={"file_id": "00000000-0000-0000-0000-000000000000"},
            headers=headers,
        )
    assert response.status_code in (404, 503)


@pytest.mark.asyncio
async def test_analyze_no_llm_keys_returns_503(user_token: str) -> None:
    """POST /analyze when LLM keys are not configured should return 503."""
    from unittest.mock import patch
    headers = {"Authorization": f"Bearer {user_token}"}
    with patch(
        "app.routers.analyze.is_pipeline_configured",
        return_value=False,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/analyze/",
                json={"file_id": "some-id"},
                headers=headers,
            )
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"].lower()


# ── History stub ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_history_authenticated_returns_empty_list(user_token: str) -> None:
    """GET /analyze/history with valid token should return empty stub list."""
    headers = {"Authorization": f"Bearer {user_token}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/analyze/history", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


# ── MockYOLOService unit tests ─────────────────────────────────────────────────

def test_mock_yolo_is_deterministic() -> None:
    """Same image bytes should always produce the same number and types of components."""
    svc = MockYOLOService()
    result_a = svc.detect(_MINIMAL_IMAGE)
    result_b = svc.detect(_MINIMAL_IMAGE)
    assert len(result_a) == len(result_b)
    types_a = [c.component_type for c in result_a]
    types_b = [c.component_type for c in result_b]
    assert types_a == types_b


def test_mock_yolo_different_images_may_differ() -> None:
    """Different image bytes should produce different components."""
    svc = MockYOLOService()
    result_a = svc.detect(_MINIMAL_IMAGE)
    result_b = svc.detect(_OTHER_IMAGE)
    types_a = sorted(c.component_type for c in result_a)
    types_b = sorted(c.component_type for c in result_b)
    assert types_a != types_b


def test_mock_yolo_confidence_in_range() -> None:
    """All detection confidences should be in [0.60, 0.95]."""
    svc = MockYOLOService()
    components = svc.detect(_MINIMAL_IMAGE)
    assert components, "Expected at least one component"
    for c in components:
        assert 0.60 <= c.detection_confidence <= 0.95, (
            f"Confidence {c.detection_confidence} out of range for {c.component_type}"
        )


# ── MockMaterialClassifierService unit tests ──────────────────────────────────

@pytest.mark.asyncio
async def test_mock_material_is_deterministic() -> None:
    """Same image bytes should always produce the same material distribution."""
    svc = MockMaterialClassifierService()
    result_a = await svc.classify(_MINIMAL_IMAGE)
    result_b = await svc.classify(_MINIMAL_IMAGE)
    assert result_a.dominant == result_b.dominant
    assert result_a.distribution == result_b.distribution


@pytest.mark.asyncio
async def test_mock_material_distribution_sums_to_one() -> None:
    """Material distribution probabilities should sum to ~1.0."""
    svc = MockMaterialClassifierService()
    result = await svc.classify(_MINIMAL_IMAGE)
    total = sum(result.distribution.values())
    assert abs(total - 1.0) < 1e-3, f"Distribution sum {total} not ~1.0"


@pytest.mark.asyncio
async def test_mock_material_dominant_matches_max_prob() -> None:
    """Dominant material should be the one with max probability."""
    svc = MockMaterialClassifierService()
    result = await svc.classify(_MINIMAL_IMAGE)
    expected = max(result.distribution, key=lambda k: result.distribution[k])
    assert result.dominant == expected
    assert result.confidence == result.distribution[expected]


@pytest.mark.asyncio
async def test_mock_material_uses_all_classes() -> None:
    """Distribution should contain all 5 material classes."""
    svc = MockMaterialClassifierService()
    result = await svc.classify(_MINIMAL_IMAGE)
    assert set(result.distribution.keys()) == set(MATERIAL_CLASSES)


# ── GeminiMaterialClassifierService unit tests ───────────────────────────────

class _StubVisionLLM:
    """Stub GeminiService returning a fixed raw response for material tests."""

    def __init__(self, raw_response: str) -> None:
        self._raw_response = raw_response

    async def generate_with_image(
        self, prompt: str, image_base64: str, temperature: float = 0.0
    ) -> str:
        """Return the canned response regardless of inputs."""
        return self._raw_response


@pytest.mark.asyncio
async def test_gemini_material_parses_valid_json() -> None:
    """Valid Gemini JSON yields a normalised 5-class distribution + observed list."""
    from chatbot.services.gemini_material_service import (
        GeminiMaterialClassifierService,
    )

    raw = (
        '{"distribution": {"concrete": 0.6, "glass": 0.2, "stone": 0.1, '
        '"brick": 0.05, "metal": 0.05}, '
        '"observed_materials": ["exposed concrete", "weathered steel"]}'
    )
    svc = GeminiMaterialClassifierService(_StubVisionLLM(raw))
    result = await svc.classify(_MINIMAL_IMAGE)
    assert set(result.distribution.keys()) == set(MATERIAL_CLASSES)
    assert abs(sum(result.distribution.values()) - 1.0) < 1e-3
    assert result.dominant == "concrete"
    assert result.confidence == result.distribution["concrete"]
    assert result.observed_materials == ["exposed concrete", "weathered steel"]


@pytest.mark.asyncio
async def test_gemini_material_filters_unknown_and_clips_negatives() -> None:
    """Out-of-vocab keys are dropped, negative scores clipped, then re-normalised."""
    from chatbot.services.gemini_material_service import (
        GeminiMaterialClassifierService,
    )

    raw = (
        '{"distribution": {"concrete": 0.5, "glass": -0.3, "wood": 0.9, '
        '"stone": 0.5}, "observed_materials": ["timber"]}'
    )
    svc = GeminiMaterialClassifierService(_StubVisionLLM(raw))
    result = await svc.classify(_MINIMAL_IMAGE)
    assert set(result.distribution.keys()) == set(MATERIAL_CLASSES)
    assert abs(sum(result.distribution.values()) - 1.0) < 1e-3
    # glass clipped to 0, wood dropped; mass split between concrete & stone.
    assert result.distribution["glass"] == 0.0
    assert result.distribution["concrete"] == 0.5
    assert result.distribution["stone"] == 0.5
    assert result.observed_materials == ["timber"]


@pytest.mark.asyncio
async def test_gemini_material_bad_json_falls_back_to_uniform() -> None:
    """A non-JSON / unusable response degrades to a uniform distribution."""
    from chatbot.services.gemini_material_service import (
        GeminiMaterialClassifierService,
    )

    svc = GeminiMaterialClassifierService(_StubVisionLLM("sorry, I cannot help"))
    result = await svc.classify(_MINIMAL_IMAGE)
    assert set(result.distribution.keys()) == set(MATERIAL_CLASSES)
    assert abs(sum(result.distribution.values()) - 1.0) < 1e-3
    assert result.observed_materials == []


# ── MockGlobalFeatureService unit tests ──────────────────────────────────────

@pytest.mark.asyncio
async def test_mock_global_feature_is_deterministic() -> None:
    """Same image bytes should always produce the same GlobalFeatureOutput."""
    svc = MockGlobalFeatureService()
    result_a = await svc.extract(_MINIMAL_IMAGE)
    result_b = await svc.extract(_MINIMAL_IMAGE)
    assert result_a.style_prior == result_b.style_prior
    assert result_a.attributes.model_dump() == result_b.attributes.model_dump()
    assert result_a.gradcam_b64 == result_b.gradcam_b64


@pytest.mark.asyncio
async def test_mock_global_feature_returns_global_feature_output() -> None:
    """Result should be a GlobalFeatureOutput with real AttributeVector."""
    svc = MockGlobalFeatureService()
    result = await svc.extract(_MINIMAL_IMAGE)
    assert isinstance(result, GlobalFeatureOutput)
    assert isinstance(result.attributes, AttributeVector)
    assert result.gradcam_b64 is None


@pytest.mark.asyncio
async def test_mock_global_feature_prior_sums_to_one() -> None:
    """Style prior probabilities should sum to ~1.0 across all 10 styles."""
    svc = MockGlobalFeatureService()
    result = await svc.extract(_MINIMAL_IMAGE)
    total = sum(result.style_prior.values())
    assert abs(total - 1.0) < 1e-3, f"Prior sum {total} not ~1.0"


@pytest.mark.asyncio
async def test_mock_global_feature_prior_covers_all_styles() -> None:
    """Style prior should contain entries for every style in STYLE_CLASSES."""
    svc = MockGlobalFeatureService()
    result = await svc.extract(_MINIMAL_IMAGE)
    assert set(result.style_prior.keys()) == set(STYLE_CLASSES)


@pytest.mark.asyncio
async def test_mock_global_feature_different_images_diverge() -> None:
    """Different image bytes should produce different style priors."""
    svc = MockGlobalFeatureService()
    result_a = await svc.extract(_MINIMAL_IMAGE)
    result_b = await svc.extract(_OTHER_IMAGE)
    assert result_a.style_prior != result_b.style_prior


# ── compute_aggregated_votes unit test ────────────────────────────────────────

def _make_component_analysis(
    component_type: str,
    detection_confidence: float,
    style_distribution: dict,
) -> ComponentAnalysis:
    """Build a minimal ComponentAnalysis for testing vote aggregation."""
    cid = "test-id"
    return ComponentAnalysis(
        component_id=cid,
        component_type=component_type,
        detection_confidence=detection_confidence,
        agent1=Agent1Output(component_id=cid, feature_description="test"),
        agent2=Agent2Output(component_id=cid, style_distribution=style_distribution),
        agent3=Agent3Output(
            component_id=cid,
            has_contradiction=False,
            contradiction_analysis="",
            violated_rules=[],
        ),
        agent4=Agent4Output(
            component_id=cid,
            component_type=component_type,
            style="Gothic",
            confidence=0.8,
            reasoning="test",
        ),
    )


# ── _build_style_distribution_safe unit tests ────────────────────────────────

def test_build_style_distribution_mixture_normalises_and_filters_secondary() -> None:
    """3-style mixture: primary is argmax; only styles ≥ 0.15 enter secondary."""
    sd = _build_style_distribution_safe(
        {"Gothic": 0.7, "Renaissance": 0.2, "Baroque": 0.1},
        fallback_primary="Modernism",
    )
    assert sd.primary == "Gothic"
    assert sd.secondary == ["Renaissance"]  # Baroque 0.10 < threshold 0.15
    assert abs(sum(sd.distribution.values()) - 1.0) < 1e-9


def test_build_style_distribution_falls_back_on_all_unknown_styles() -> None:
    """If raw dict has no STYLE_CLASSES keys, returns 1-hot on fallback."""
    sd = _build_style_distribution_safe(
        {"Postmodern": 0.5, "Foo": 0.5},
        fallback_primary="Brutalism",
    )
    assert sd.primary == "Brutalism"
    assert sd.distribution == {"Brutalism": 1.0}
    assert sd.secondary == []


def test_build_style_distribution_drops_malformed_values() -> None:
    """Non-numeric values are coerced to 0 and the style is dropped."""
    sd = _build_style_distribution_safe(
        {"Gothic": "bad", "Renaissance": 0.6, "Baroque": 0.4},
        fallback_primary="Modernism",
    )
    assert sd.primary == "Renaissance"
    assert sd.secondary == ["Baroque"]
    assert "Gothic" not in sd.distribution


def test_build_style_distribution_single_style_has_empty_secondary() -> None:
    """1-hot distribution → no secondary styles."""
    sd = _build_style_distribution_safe(
        {"Modernism": 0.95},
        fallback_primary="Gothic",
    )
    assert sd.primary == "Modernism"
    assert sd.secondary == []


def test_build_style_distribution_clips_negative_values() -> None:
    """Negative probabilities are clipped to 0.0 then dropped."""
    sd = _build_style_distribution_safe(
        {"Gothic": -0.5, "Modernism": 0.7, "Brutalism": 0.3},
        fallback_primary="Renaissance",
    )
    assert "Gothic" not in sd.distribution
    assert sd.primary == "Modernism"


def test_compute_aggregated_votes_weighted_sum() -> None:
    """Aggregated votes should be the weighted sum of style distributions."""
    from chatbot.utils.schemas import STYLE_CLASSES
    base_dist = {s: 0.0 for s in STYLE_CLASSES}

    dist_a = dict(base_dist)
    dist_a["Gothic"] = 1.0

    dist_b = dict(base_dist)
    dist_b["Baroque"] = 1.0

    components = [
        _make_component_analysis("arch", 0.9, dist_a),
        _make_component_analysis("dome", 0.6, dist_b),
    ]
    votes = compute_aggregated_votes(components)

    assert abs(votes["Gothic"] - 0.9) < 1e-6, f"Gothic vote should be 0.9, got {votes['Gothic']}"
    assert abs(votes["Baroque"] - 0.6) < 1e-6, f"Baroque vote should be 0.6, got {votes['Baroque']}"
    assert votes["Renaissance"] == 0.0


# ── check_rules unit tests ────────────────────────────────────────────────────

def test_check_rules_arch_gothic_no_contradiction() -> None:
    """arch is shared (not exclusive) → no contradiction with any style."""
    result = check_rules("arch", "Gothic")
    assert result.has_contradiction is False
    assert result.violated_rules == []


def test_check_rules_solomonic_column_baroque_no_contradiction() -> None:
    """solomonic_column is exclusive to Baroque → no contradiction."""
    result = check_rules("solomonic_column", "Baroque")
    assert result.has_contradiction is False


def test_check_rules_solomonic_column_neoclassical_contradiction() -> None:
    """solomonic_column is exclusive to Baroque, not Neoclassical → contradiction."""
    result = check_rules("solomonic_column", "Neoclassical")
    assert result.has_contradiction is True


def test_check_rules_column_capital_neoclassical_no_contradiction() -> None:
    """column_capital is shared (not exclusive) → no contradiction."""
    result = check_rules("column_capital", "Neoclassical")
    assert result.has_contradiction is False


# ── check_material_consistency unit tests ─────────────────────────────────────

def test_check_material_concrete_brutalism_no_contradiction() -> None:
    """concrete is expected for Brutalism → returns None (no message)."""
    assert check_material_consistency("concrete", "Brutalism") is None


def test_check_material_concrete_gothic_contradiction() -> None:
    """concrete is uncommon for Gothic → returns contradiction message."""
    msg = check_material_consistency("concrete", "Gothic")
    assert msg is not None
    assert "concrete" in msg.lower()
    assert "gothic" in msg.lower()


def test_check_material_glass_hightech_no_contradiction() -> None:
    """glass + High-tech → returns None."""
    assert check_material_consistency("glass", "High-tech") is None


def test_check_material_stone_renaissance_no_contradiction() -> None:
    """stone + Renaissance → returns None."""
    assert check_material_consistency("stone", "Renaissance") is None


def test_check_material_unknown_material_no_contradiction() -> None:
    """Unknown material (not in MATERIAL_STYLE_RULES) → returns None (graceful)."""
    assert check_material_consistency("wood", "Modernism") is None

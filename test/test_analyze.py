"""Test suite for the open-vocabulary analysis endpoints + runner helpers.

Run with: pytest test/ -v

Groups:
- Auth guards   : no token → 403 on both endpoints
- 404 / 503     : unknown file_id → 404/503; LLM not configured → 503
- History       : authenticated user → 200 (empty list under the mocked DB)
- runner helpers: _build_style_distribution_safe / _build_evidence_votes /
                  _fallback_primary (pure functions, no LLM)
"""
import io

import pytest
from PIL import Image
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app
from app.security.security import create_access_token
from chatbot.services.pipeline_runner import (
    PipelineRunner,
    _build_evidence_votes,
    _fallback_primary,
)
from chatbot.utils.distribution import (
    build_style_distribution_safe as _build_style_distribution_safe,
)
from chatbot.utils.schemas import (
    EvidenceItem,
    EvidenceSheet,
    PanelVerdict,
    PipelineInput,
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
    """POST /analyze with a non-existent file_id should return 404 (or 503 if no keys)."""
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
    with patch("app.routers.analyze.is_pipeline_configured", return_value=False):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/analyze/",
                json={"file_id": "some-id"},
                headers=headers,
            )
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"].lower()


# ── History ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_history_authenticated_returns_empty_list(user_token: str) -> None:
    """GET /analyze/history with valid token should return empty list under mock DB."""
    headers = {"Authorization": f"Bearer {user_token}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/analyze/history", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


# ── _build_style_distribution_safe (open-vocabulary) ──────────────────────────

def test_build_style_distribution_open_vocab_normalises_and_filters_secondary() -> None:
    """allowed=None accepts any name; primary is argmax, secondary needs ≥ 0.15."""
    sd = _build_style_distribution_safe(
        {"Mughal": 0.7, "Persian": 0.2, "Timurid": 0.1},
        fallback_primary="Unknown",
        allowed=None,
    )
    assert sd.primary == "Mughal"
    assert sd.secondary == ["Persian"]  # Timurid 0.10 < threshold 0.15
    assert abs(sum(sd.distribution.values()) - 1.0) < 1e-9


def test_build_style_distribution_constrains_to_allowed_candidates() -> None:
    """Names outside the allowed candidate set are dropped before normalising."""
    sd = _build_style_distribution_safe(
        {"Gothic": 0.5, "MadeUpStyle": 0.5},
        fallback_primary="Romanesque",
        allowed={"Gothic", "Romanesque"},
    )
    assert sd.primary == "Gothic"
    assert sd.distribution == {"Gothic": 1.0}


def test_build_style_distribution_allowed_match_is_case_insensitive() -> None:
    """A lowercase LLM key maps back to the canonical candidate spelling."""
    sd = _build_style_distribution_safe(
        {"gothic": 0.8, "romanesque": 0.2},
        fallback_primary="Gothic",
        allowed={"Gothic", "Romanesque"},
    )
    assert sd.primary == "Gothic"
    assert set(sd.distribution.keys()) == {"Gothic", "Romanesque"}


def test_build_style_distribution_falls_back_when_all_filtered() -> None:
    """If nothing matches the allowed set, returns 1-hot on fallback_primary."""
    sd = _build_style_distribution_safe(
        {"Foo": 0.5, "Bar": 0.5},
        fallback_primary="Brutalism",
        allowed={"Gothic"},
    )
    assert sd.primary == "Brutalism"
    assert sd.distribution == {"Brutalism": 1.0}
    assert sd.secondary == []


def test_build_style_distribution_clips_negatives_and_drops_malformed() -> None:
    """Negative probabilities clipped to 0; non-numeric values coerced to 0."""
    sd = _build_style_distribution_safe(
        {"Gothic": -0.5, "Baroque": "bad", "Renaissance": 0.7, "Mannerism": 0.3},
        fallback_primary="Unknown",
        allowed=None,
    )
    assert "Gothic" not in sd.distribution
    assert "Baroque" not in sd.distribution
    assert sd.primary == "Renaissance"


# ── _build_evidence_votes / _fallback_primary ─────────────────────────────────

def _sheet(*style_lists: list) -> EvidenceSheet:
    """Build an EvidenceSheet whose items each suggest the given styles."""
    items = [
        EvidenceItem(dimension=f"d{i}", feature="f", suggested_styles=styles)
        for i, styles in enumerate(style_lists)
    ]
    return EvidenceSheet(items=items)


def test_build_evidence_votes_counts_frequency_not_confidence() -> None:
    """Each dimension contributes one vote per suggested style; result sums to 1."""
    votes = _build_evidence_votes(_sheet(["Gothic"], ["Gothic", "Romanesque"], ["Gothic"]))
    # Gothic appears in 3 dimensions, Romanesque in 1 → 3:1 ratio.
    assert votes["Gothic"] > votes["Romanesque"]
    assert abs(votes["Gothic"] - 0.75) < 1e-9
    assert abs(sum(votes.values()) - 1.0) < 1e-9


def test_build_evidence_votes_empty_sheet_is_empty() -> None:
    """An empty evidence sheet yields no votes."""
    assert _build_evidence_votes(EvidenceSheet()) == {}


def test_fallback_primary_prefers_top_voted_candidate() -> None:
    """The fallback picks the candidate with the most evidence support."""
    votes = {"Gothic": 0.75, "Romanesque": 0.25}
    assert _fallback_primary(votes, ["Romanesque", "Gothic"]) == "Gothic"


def test_fallback_primary_handles_no_candidates() -> None:
    """With no candidates, falls back to the top vote, else 'Unknown'."""
    assert _fallback_primary({"Khmer": 1.0}, []) == "Khmer"
    assert _fallback_primary({}, []) == "Unknown"


# ── Runner: panel → consensus → arbiter → abstention ──────────────────────────

_CANDS = ["Gothic", "Romanesque", "Baroque"]


def _verdict(judge: str, dist: dict) -> PanelVerdict:
    """Build a PanelVerdict with a validated distribution over the candidates."""
    sd = _build_style_distribution_safe(dist, "Gothic", set(_CANDS))
    return PanelVerdict(judge=judge, model_id="stub", style_distribution=sd, reasoning="r")


class _StubPanel:
    """Panel stub returning fixed verdicts; records the on_run callback fires."""

    def __init__(self, verdicts) -> None:
        self._verdicts = verdicts

    async def judge(self, sheet, candidate_names, kb_text, evidence_votes,
                    allowed, fallback_primary, full_image_base64=None, on_run=None):
        if on_run is not None:
            for v in self._verdicts:
                on_run(f"Panel: {v.judge}", v.model_id, 1.0, not v.failed)
        return self._verdicts


class _StubArbiter:
    """Arbiter stub: fenced-JSON verdict from chat_structured."""

    async def chat_structured(self, prompt, image_base64=None) -> str:
        return (
            "```json\n"
            '{"style_distribution": {"Gothic": 0.8, "Romanesque": 0.2}, '
            '"composition_explanation": "x", '
            '"evidence_per_style": {"Gothic": ["a", "b"], "Romanesque": ["c", "d"]}}\n'
            "```"
        )


class _StubText:
    """DeepSeek text-LLM stub for the translation pass."""

    def __init__(self, raw: str = "{}") -> None:
        self._raw = raw

    async def chat(self, prompt, temperature=0.3, json_mode=False) -> str:
        return self._raw


class _StubHybridArbiter:
    """Arbiter stub returning a multi-style mixture (≥ 2 significant styles)."""

    async def chat_structured(self, prompt, image_base64=None) -> str:
        return (
            "```json\n"
            '{"style_distribution": {"Gothic": 0.55, "Romanesque": 0.3, "Baroque": 0.15}, '
            '"composition_explanation": "hybrid", '
            '"evidence_per_style": {"Gothic": ["a", "b"], "Romanesque": ["c", "d"]}}\n'
            "```"
        )


def _pipeline_input(extraction_agreement=None, extraction_completeness=1.0) -> PipelineInput:
    sheet = EvidenceSheet(
        items=[EvidenceItem(dimension="arch", feature="round", suggested_styles=["Romanesque"])],
        proposed_styles=["Romanesque"],
    )
    return PipelineInput(
        evidence_sheet=sheet, candidate_names=_CANDS, candidate_kb_text="",
        full_image_base64=None, extraction_agreement=extraction_agreement,
        extraction_completeness=extraction_completeness,
    )


@pytest.mark.asyncio
async def test_runner_low_agreement_marks_uncertain() -> None:
    """Judges that disagree (mean Spearman < threshold) → uncertain=True."""
    verdicts = [
        _verdict("gemini", {"Gothic": 0.6, "Romanesque": 0.3, "Baroque": 0.1}),
        _verdict("deepseek", {"Gothic": 0.1, "Romanesque": 0.3, "Baroque": 0.6}),
        _verdict("openai", {"Gothic": 0.3, "Romanesque": 0.6, "Baroque": 0.1}),
    ]
    runner = PipelineRunner(_StubPanel(verdicts), _StubArbiter(), _StubText())
    result = await runner.run(_pipeline_input())
    assert result.panel_agreement is not None and result.panel_agreement < 0.5
    assert result.uncertain is True
    assert len(result.panel_verdicts) == 3
    # Telemetry: 3 judges + 1 arbiter recorded.
    assert len(result.agent_runs) == 4


@pytest.mark.asyncio
async def test_runner_high_agreement_not_uncertain() -> None:
    """Judges that concur (and a confident mixture) → uncertain=False."""
    verdicts = [
        _verdict("gemini", {"Gothic": 0.7, "Romanesque": 0.2, "Baroque": 0.1}),
        _verdict("deepseek", {"Gothic": 0.6, "Romanesque": 0.3, "Baroque": 0.1}),
        _verdict("openai", {"Gothic": 0.8, "Romanesque": 0.15, "Baroque": 0.05}),
    ]
    runner = PipelineRunner(_StubPanel(verdicts), _StubArbiter(), _StubText())
    result = await runner.run(_pipeline_input())
    assert result.panel_agreement == 1.0
    assert result.uncertain is False
    assert result.style == "Gothic"


@pytest.mark.asyncio
async def test_runner_translate_populates_vi_fields() -> None:
    """runner.translate() fills the *_vi narrative fields from the text LLM."""
    translation = (
        '{"explanation": "Giai thich tieng Viet", '
        '"key_evidence": ["bang chung 1"], '
        '"composition_explanation": "Bo cuc", '
        '"evidence_per_style": {"Gothic": ["chi tiet"]}}'
    )
    runner = PipelineRunner(_StubPanel([]), _StubArbiter(), _StubText(translation))
    vi, _sheet_vi = await runner.translate(
        explanation="x", key_evidence=["y"], composition_explanation="z",
        evidence_per_style={"Gothic": ["e"]}, evidence_sheet=None,
    )
    assert vi["explanation_vi"] == "Giai thich tieng Viet"
    assert vi["key_evidence_vi"] == ["bang chung 1"]
    assert vi["composition_explanation_vi"] == "Bo cuc"


@pytest.mark.asyncio
async def test_runner_translate_evidence_sheet() -> None:
    """runner.translate() returns a translated 12-dim evidence sheet."""
    sheet = EvidenceSheet(
        items=[
            EvidenceItem(dimension="arch", feature="round arch", suggested_styles=["Romanesque"])
        ],
        overall_note="note",
    )
    translation = (
        '{"explanation": "Giai thich", "key_evidence": ["bc"], '
        '"composition_explanation": "bc", "evidence_per_style": {"Gothic": ["x"]}, '
        '"overall_note": "tong quan", '
        '"evidence_items": [{"i": 0, "feature": "vom tron", "note": "ghi chu"}]}'
    )
    runner = PipelineRunner(_StubPanel([]), _StubArbiter(), _StubText(translation))
    _vi, sheet_vi = await runner.translate(
        explanation="x", key_evidence=["y"], composition_explanation="z",
        evidence_per_style=None, evidence_sheet=sheet,
    )
    assert sheet_vi is not None
    assert sheet_vi.items[0].feature == "vom tron"
    # dimension + suggested_styles are preserved (only feature/note translated).
    assert sheet_vi.items[0].dimension == "arch"
    assert sheet_vi.items[0].suggested_styles == ["Romanesque"]


@pytest.mark.asyncio
async def test_runner_translates_evidence_sheet_in_batches() -> None:
    """A 13-item sheet is translated across batches and merged back by index."""
    import json as _json
    import re

    items = [
        EvidenceItem(dimension="diagnostic", feature=f"feat {n}", suggested_styles=[])
        for n in range(13)
    ]
    sheet = EvidenceSheet(items=items, overall_note="note")

    class _BatchText:
        """Echoes each batch's items back as Vietnamese, keyed by index."""

        async def chat(self, prompt, temperature=0.3, json_mode=False) -> str:
            idxs = [int(m) for m in re.findall(r'"i":\s*(\d+)', prompt)]
            if idxs:
                return _json.dumps({
                    "evidence_items": [{"i": i, "feature": f"vi {i}", "note": None} for i in idxs]
                })
            return _json.dumps({"overall_note": "tong quan"})

    runner = PipelineRunner(_StubPanel([]), _StubArbiter(), _BatchText())
    _vi, sheet_vi = await runner.translate(
        explanation="x", key_evidence=["y"], composition_explanation="z",
        evidence_per_style=None, evidence_sheet=sheet,
    )
    assert sheet_vi is not None
    assert len(sheet_vi.items) == 13
    # Every item is translated, including those in the 2nd/3rd batches.
    assert all(it.feature == f"vi {i}" for i, it in enumerate(sheet_vi.items))
    assert sheet_vi.overall_note == "tong quan"


@pytest.mark.asyncio
async def test_runner_defers_translation_by_default(monkeypatch) -> None:
    """With DEFER_TRANSLATION (default) run() returns English only (*_vi = None)."""
    monkeypatch.setattr(settings, "DEFER_TRANSLATION", True)
    runner = PipelineRunner(_StubPanel(_agreeing_verdicts()), _StubArbiter(), _StubText("{}"))
    result = await runner.run(_pipeline_input())
    assert result.explanation_vi is None
    assert result.evidence_sheet_vi is None


@pytest.mark.asyncio
async def test_runner_inline_translation_when_not_deferred(monkeypatch) -> None:
    """DEFER_TRANSLATION=False → run() still translates inline (rollback path)."""
    monkeypatch.setattr(settings, "DEFER_TRANSLATION", False)
    translation = (
        '{"explanation": "Giai thich tieng Viet", "key_evidence": ["bc"], '
        '"composition_explanation": "Bo cuc", "evidence_per_style": {"Gothic": ["x"]}}'
    )
    runner = PipelineRunner(
        _StubPanel(_agreeing_verdicts()), _StubArbiter(), _StubText(translation)
    )
    result = await runner.run(_pipeline_input())
    assert result.explanation_vi == "Giai thich tieng Viet"


# ── Runner: hybrid (multi-style) detection — independent of uncertainty ────────

def _agreeing_verdicts():
    """Three judges that concur on the ranking (high agreement → not uncertain)."""
    return [
        _verdict("gemini", {"Gothic": 0.7, "Romanesque": 0.2, "Baroque": 0.1}),
        _verdict("deepseek", {"Gothic": 0.6, "Romanesque": 0.3, "Baroque": 0.1}),
        _verdict("openai", {"Gothic": 0.8, "Romanesque": 0.15, "Baroque": 0.05}),
    ]


@pytest.mark.asyncio
async def test_runner_mixture_with_two_significant_styles_marks_hybrid() -> None:
    """An arbiter mixture with ≥ 2 significant styles → hybrid=True, not uncertain."""
    runner = PipelineRunner(
        _StubPanel(_agreeing_verdicts()), _StubHybridArbiter(), _StubText()
    )
    result = await runner.run(_pipeline_input())
    # ≥ 2 styles clear HYBRID_MASS_MIN → flagged hybrid from the mixture itself.
    assert result.hybrid is True


@pytest.mark.asyncio
async def test_runner_low_extraction_agreement_marks_hybrid() -> None:
    """Disagreeing extraction calls → hybrid even when the arbiter is single-dominant."""
    runner = PipelineRunner(
        _StubPanel(_agreeing_verdicts()), _StubArbiter(), _StubText()
    )
    # _StubArbiter returns {Gothic 0.8, Romanesque 0.2} → only 1 significant style;
    # the hybrid flag must come from the low extraction_agreement instead.
    result = await runner.run(_pipeline_input(extraction_agreement=0.2))
    assert result.hybrid is True
    assert result.extraction_agreement == 0.2
    # Hybrid is INDEPENDENT of abstention: this confident answer stays not-uncertain.
    assert result.uncertain is False


@pytest.mark.asyncio
async def test_runner_single_dominant_high_extraction_not_hybrid() -> None:
    """A single-dominant mixture with high extraction agreement → hybrid=False."""
    runner = PipelineRunner(
        _StubPanel(_agreeing_verdicts()), _StubArbiter(), _StubText()
    )
    result = await runner.run(_pipeline_input(extraction_agreement=0.9))
    assert result.hybrid is False
    assert result.uncertain is False


# ── Runner: recall escape hatch (A2) + run-quality confidence (A3) ─────────────

class _StubEscapeArbiter:
    """Arbiter that names a style OUTSIDE the candidate set (Moorish Revival)."""

    async def chat_structured(self, prompt, image_base64=None) -> str:
        return (
            "```json\n"
            '{"style_distribution": {"Moorish Revival": 0.7, "Gothic": 0.3}, '
            '"composition_explanation": "x", '
            '"evidence_per_style": {"Gothic": ["a", "b"]}}\n'
            "```"
        )


class _KbEntry:
    """Minimal KB entry exposing the canonical ``name``."""

    def __init__(self, name: str) -> None:
        self.name = name


class _StubKb:
    """KB stub: matches a name to its canonical entry and reports feature support.

    ``supported`` lists the canonical names the observed evidence backs (the
    escape-hatch evidence gate, ``retrieve_by_features``). Defaults to every
    mapped name so the plain name-match behaviour is preserved unless a test
    deliberately withholds support.
    """

    def __init__(self, mapping: dict, supported=None) -> None:
        self._mapping = mapping
        self._supported = (
            list(mapping.values()) if supported is None else list(supported)
        )

    def match(self, name: str):
        canon = self._mapping.get(name.strip().lower())
        return _KbEntry(canon) if canon else None

    def retrieve_by_features(self, observed_features, top_n: int):
        return [_KbEntry(n) for n in self._supported][:top_n]


@pytest.mark.asyncio
async def test_runner_escape_hatch_admits_kb_matched_style() -> None:
    """A KB-matched, evidence-backed style proposed outside candidates enters."""
    kb = _StubKb({"moorish revival": "Moorish Revival"})
    runner = PipelineRunner(
        _StubPanel(_agreeing_verdicts()), _StubEscapeArbiter(), _StubText(), kb=kb
    )
    result = await runner.run(_pipeline_input())
    assert "Moorish Revival" in result.style_distribution.distribution


@pytest.mark.asyncio
async def test_runner_escape_hatch_drops_kb_match_without_evidence() -> None:
    """A KB-matched style the evidence does NOT back is rejected (evidence gate)."""
    # Maps the name but reports NO feature support → must not be admitted.
    kb = _StubKb({"moorish revival": "Moorish Revival"}, supported=[])
    runner = PipelineRunner(
        _StubPanel(_agreeing_verdicts()), _StubEscapeArbiter(), _StubText(), kb=kb
    )
    result = await runner.run(_pipeline_input())
    assert "Moorish Revival" not in result.style_distribution.distribution


@pytest.mark.asyncio
async def test_runner_escape_hatch_drops_unmatched_style_without_kb() -> None:
    """Without a KB (or no match), an out-of-candidate style is dropped."""
    runner = PipelineRunner(
        _StubPanel(_agreeing_verdicts()), _StubEscapeArbiter(), _StubText()
    )
    result = await runner.run(_pipeline_input())
    assert "Moorish Revival" not in result.style_distribution.distribution


@pytest.mark.asyncio
async def test_runner_confidence_discounted_by_run_quality() -> None:
    """Lost extraction calls (lower completeness) discount the reported confidence."""
    runner = PipelineRunner(
        _StubPanel(_agreeing_verdicts()), _StubArbiter(), _StubText()
    )
    full = await runner.run(
        _pipeline_input(extraction_agreement=0.9, extraction_completeness=1.0)
    )
    degraded = await runner.run(
        _pipeline_input(extraction_agreement=0.9, extraction_completeness=0.5)
    )
    assert degraded.confidence < full.confidence


@pytest.mark.asyncio
async def test_runner_records_raw_and_parsed_telemetry() -> None:
    """The arbiter AgentRun now carries raw + parsed output (was all-NULL before)."""
    runner = PipelineRunner(
        _StubPanel(_agreeing_verdicts()), _StubArbiter(), _StubText()
    )
    result = await runner.run(_pipeline_input())
    arb = next(r for r in result.agent_runs if r.agent_name == "Arbiter")
    assert arb.raw_output and "style_distribution" in arb.raw_output
    assert arb.parsed_output and "Gothic" in arb.parsed_output


# ── Runner: arbiter provider fallback + run_status (A4b) ───────────────────────

class _FailingArbiter:
    """Primary arbiter whose call always fails (simulates a provider outage)."""

    async def chat_structured(self, prompt, image_base64=None) -> str:
        raise RuntimeError("openai arbiter down")


class _StubGeminiArbiter:
    """Gemini stub acting as the arbiter fallback — returns a fenced-JSON verdict."""

    async def generate_with_image(
        self, prompt, image_base64="", temperature=0.4, json_mode=False
    ) -> str:
        return (
            "```json\n"
            '{"style_distribution": {"Gothic": 0.9, "Romanesque": 0.1}, '
            '"composition_explanation": "from gemini fallback"}\n'
            "```"
        )


def _image_pipeline_input(extraction_completeness=1.0) -> PipelineInput:
    """Pipeline input WITH an image so the arbiter fallback chain is active."""
    sheet = EvidenceSheet(
        items=[EvidenceItem(dimension="arch", feature="round", suggested_styles=["Romanesque"])],
        proposed_styles=["Romanesque"],
    )
    return PipelineInput(
        evidence_sheet=sheet, candidate_names=_CANDS, candidate_kb_text="",
        full_image_base64="aW1n", extraction_agreement=0.9,
        extraction_completeness=extraction_completeness,
    )


@pytest.mark.asyncio
async def test_runner_arbiter_falls_back_to_gemini() -> None:
    """OpenAI arbiter down → Gemini answers the arbiter role; run marked degraded."""
    runner = PipelineRunner(
        _StubPanel(_agreeing_verdicts()), _FailingArbiter(), _StubText(),
        gemini_llm=_StubGeminiArbiter(),
    )
    result = await runner.run(_image_pipeline_input())
    assert result.style == "Gothic"
    # It was the gemini FALLBACK, not the panel-average last resort.
    assert any("fallback provider: gemini" in w for w in result.warnings)
    assert not any("panel-average fallback" in w for w in result.warnings)
    assert result.run_status == "degraded"


@pytest.mark.asyncio
async def test_runner_run_status_completed_on_healthy_run() -> None:
    """All judges + extraction calls succeed and openai answers → completed."""
    runner = PipelineRunner(
        _StubPanel(_agreeing_verdicts()), _StubArbiter(), _StubText()
    )
    result = await runner.run(
        _pipeline_input(extraction_agreement=0.9, extraction_completeness=1.0)
    )
    assert result.run_status == "completed"


@pytest.mark.asyncio
async def test_runner_run_status_degraded_on_lost_extraction() -> None:
    """A lost extraction call (completeness < 1) marks the run degraded."""
    runner = PipelineRunner(
        _StubPanel(_agreeing_verdicts()), _StubArbiter(), _StubText()
    )
    result = await runner.run(
        _pipeline_input(extraction_agreement=0.9, extraction_completeness=0.5)
    )
    assert result.run_status == "degraded"

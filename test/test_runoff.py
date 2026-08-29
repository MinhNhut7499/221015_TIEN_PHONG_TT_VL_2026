"""Tests for the contrastive run-off stage (conversion lever).

Two layers, both LLM-free:

- ``_apply_runoff`` — the pure multiplicative fusion of a run-off verdict into a
  mixture's top-2 (confident verdict flips, a strong lead survives a mild one).
- ``PipelineRunner._runoff`` — the trigger/guard logic (margin gate, KB lookup,
  disabled flag), with the vision call (``_runoff_verdict``) stubbed so no LLM is
  hit.
"""
import pytest
from unittest.mock import MagicMock

from app.config import settings
from chatbot.services.pipeline_runner import PipelineRunner, _apply_runoff
from chatbot.services.style_kb_service import get_style_kb
from chatbot.utils.schemas import StyleDistribution


def _runner(grok=None, gemini=None) -> PipelineRunner:
    """A runner with a real KB; panel/arbiter/text are unused mocks here."""
    return PipelineRunner(
        panel=MagicMock(),
        arbiter_llm=MagicMock(),
        text_llm=MagicMock(),
        kb=get_style_kb(),
        gemini_llm=gemini,
        grok_llm=grok,
    )


def _final(dist: dict) -> dict:
    """Wrap a raw distribution into the arbiter-result dict shape ``_runoff`` reads."""
    primary = max(dist, key=dist.get)
    return {
        "style": primary,
        "confidence": dist[primary],
        "style_distribution": StyleDistribution(
            distribution=dist, primary=primary, secondary=[]
        ),
        "evidence_per_style": {primary: ["x"]},
        "key_evidence": ["x"],
        "composition_explanation": "narrative",
    }


# ── _apply_runoff (pure fusion) ───────────────────────────────────────────────

def test_apply_runoff_confident_verdict_flips_winner() -> None:
    """A confident run-off (0.2/0.8) overturns a small arbiter lead."""
    out = _apply_runoff({"Moorish": 0.55, "Mughal": 0.45}, "Moorish", "Mughal", 0.2, 0.8)
    assert out["Mughal"] > out["Moorish"]


def test_apply_runoff_strong_lead_survives_mild_verdict() -> None:
    """A large arbiter lead is NOT flipped by a mild run-off (guard protection)."""
    out = _apply_runoff({"A": 0.7, "B": 0.3}, "A", "B", 0.4, 0.6)
    assert out["A"] > out["B"]


def test_apply_runoff_preserves_combined_mass_and_others() -> None:
    """Top-2 keep their COMBINED mass; every other style is untouched."""
    out = _apply_runoff({"A": 0.5, "B": 0.3, "C": 0.2}, "A", "B", 0.1, 0.9)
    assert out["C"] == 0.2
    assert abs((out["A"] + out["B"]) - 0.8) < 1e-9


def test_apply_runoff_no_signal_returns_unchanged() -> None:
    """A run-off with no usable mass (0/0) leaves the mixture unchanged."""
    src = {"A": 0.5, "B": 0.5}
    assert _apply_runoff(src, "A", "B", 0.0, 0.0) == src


# ── PipelineRunner._runoff (trigger / guard) ─────────────────────────────────

@pytest.mark.asyncio
async def test_runoff_skips_when_margin_decisive(monkeypatch) -> None:
    """A decisive top-2 margin (≥ RUNOFF_MARGIN_MAX) skips the vision call."""
    monkeypatch.setattr(settings, "RUNOFF_ENABLED", True)
    monkeypatch.setattr(settings, "RUNOFF_MARGIN_MAX", 0.30)
    runner = _runner()
    called = []

    async def _stub(*_a, **_k):
        called.append(1)
        return (0.1, 0.9)

    monkeypatch.setattr(runner, "_runoff_verdict", _stub)
    final = _final({"Gothic": 0.8, "Romanesque": 0.2})  # margin 0.6
    out = await runner._runoff(final, None, "imgdata")
    assert out["style"] == "Gothic"
    assert not called  # never reached the vision call


@pytest.mark.asyncio
async def test_runoff_triggers_and_flips_on_confident_verdict(monkeypatch) -> None:
    """A close margin triggers run-off; a confident verdict flips the primary."""
    monkeypatch.setattr(settings, "RUNOFF_ENABLED", True)
    monkeypatch.setattr(settings, "RUNOFF_MARGIN_MAX", 0.30)
    runner = _runner()

    async def _stub(entry_a, entry_b, _sheet, _img):
        return (0.1, 0.9)  # strongly favour the runner-up

    monkeypatch.setattr(runner, "_runoff_verdict", _stub)
    final = _final({"Moorish": 0.52, "Mughal": 0.48})  # margin 0.04
    out = await runner._runoff(final, None, "imgdata")
    assert out["style"] == "Mughal"
    assert out["style_distribution"].primary == "Mughal"
    # key_evidence re-points to the new primary's bullets when available.
    assert out["composition_explanation"] == "narrative"


@pytest.mark.asyncio
async def test_runoff_disabled_returns_final_unchanged(monkeypatch) -> None:
    """With RUNOFF_ENABLED off, run-off is a no-op."""
    monkeypatch.setattr(settings, "RUNOFF_ENABLED", False)
    runner = _runner()
    final = _final({"Moorish": 0.52, "Mughal": 0.48})
    out = await runner._runoff(final, None, "imgdata")
    assert out is final


@pytest.mark.asyncio
async def test_runoff_skips_when_finalist_not_in_kb(monkeypatch) -> None:
    """If a finalist does not resolve to a KB entry, run-off is skipped."""
    monkeypatch.setattr(settings, "RUNOFF_ENABLED", True)
    monkeypatch.setattr(settings, "RUNOFF_MARGIN_MAX", 0.30)
    runner = _runner()
    called = []

    async def _stub(*_a, **_k):
        called.append(1)
        return (0.1, 0.9)

    monkeypatch.setattr(runner, "_runoff_verdict", _stub)
    final = _final({"Nonexistent Style ZZZ": 0.52, "Mughal": 0.48})
    out = await runner._runoff(final, None, "imgdata")
    assert out["style"] == "Nonexistent Style ZZZ"
    assert not called


@pytest.mark.asyncio
async def test_runoff_no_image_is_noop(monkeypatch) -> None:
    """No image → no vision possible → run-off skipped."""
    monkeypatch.setattr(settings, "RUNOFF_ENABLED", True)
    runner = _runner()
    final = _final({"Moorish": 0.52, "Mughal": 0.48})
    out = await runner._runoff(final, None, None)
    assert out is final

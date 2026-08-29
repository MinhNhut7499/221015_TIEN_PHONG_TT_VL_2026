"""Tests for the judging panel (chatbot/services/style_panel.py).

The three VISION judges (Gemini / OpenAI / Grok) are stubbed (no network). Each
judge now receives the image alongside the evidence sheet, so the stubs expose
the vision call each service uses. Covers: collecting one verdict per judge,
isolating a failed judge, constraining to the allowed candidate set, marking a
judge with no usable distribution as failed, and firing the telemetry callback
once per judge.
"""
import pytest

from chatbot.services.style_panel import StylePanel
from chatbot.utils.schemas import EvidenceItem, EvidenceSheet

_GOTHIC = '{"style_distribution": {"Gothic": 0.8, "Romanesque": 0.2}, "reasoning": "r"}'
_MIXED = '{"style_distribution": {"Gothic": 0.6, "Romanesque": 0.4}, "reasoning": "r"}'
_CANDIDATES = ["Gothic", "Romanesque"]
_ALLOWED = {"Gothic", "Romanesque"}


class _StubGemini:
    """Stub GeminiService.generate_with_image returning canned text or raising."""

    def __init__(self, raw) -> None:
        self._raw = raw

    async def generate_with_image(
        self, prompt, image_base64="", temperature=0.4, json_mode=False
    ) -> str:
        if isinstance(self._raw, Exception):
            raise self._raw
        return self._raw


class _StubChat:
    """Stub for OpenAI/Grok chat_structured returning canned text or raising."""

    def __init__(self, raw) -> None:
        self._raw = raw

    async def chat_structured(self, prompt, image_base64=None, json_mode=False) -> str:
        if isinstance(self._raw, Exception):
            raise self._raw
        return self._raw


def _panel(gemini_raw, openai_raw, grok_raw) -> StylePanel:
    """Build a StylePanel from three canned vision responses (Gemini/OpenAI/Grok)."""
    return StylePanel(_StubGemini(gemini_raw), _StubChat(openai_raw), _StubChat(grok_raw))


def _sheet() -> EvidenceSheet:
    return EvidenceSheet(
        items=[EvidenceItem(dimension="arch", feature="pointed", suggested_styles=["Gothic"])],
        proposed_styles=["Gothic"],
    )


async def _judge(panel: StylePanel, on_run=None):
    return await panel.judge(
        _sheet(), _CANDIDATES, "", {"Gothic": 1.0}, _ALLOWED, "Gothic",
        full_image_base64="aW1n", on_run=on_run,
    )


@pytest.mark.asyncio
async def test_panel_collects_one_verdict_per_judge() -> None:
    """All three judges succeed → three non-failed verdicts."""
    verdicts = await _judge(_panel(_GOTHIC, _GOTHIC, _MIXED))
    assert len(verdicts) == 3
    assert all(not v.failed and v.style_distribution is not None for v in verdicts)
    assert {v.judge for v in verdicts} == {"gemini", "openai", "grok"}


@pytest.mark.asyncio
async def test_failed_judge_is_isolated_not_fatal() -> None:
    """A judge raising an error yields failed=True; the others still succeed."""
    verdicts = await _judge(_panel(_GOTHIC, RuntimeError("boom"), _MIXED))
    failed = [v for v in verdicts if v.failed]
    assert len(failed) == 1 and failed[0].judge == "openai"
    assert failed[0].style_distribution is None
    assert len([v for v in verdicts if not v.failed]) == 2


@pytest.mark.asyncio
async def test_verdict_constrained_to_allowed_candidates() -> None:
    """A style outside the allowed set is dropped from the judge's mixture."""
    rogue = '{"style_distribution": {"Gothic": 0.5, "MadeUp": 0.5}, "reasoning": "r"}'
    verdicts = await _judge(_panel(rogue, _GOTHIC, _GOTHIC))
    gem = next(v for v in verdicts if v.judge == "gemini")
    assert "MadeUp" not in gem.style_distribution.distribution


@pytest.mark.asyncio
async def test_missing_distribution_marks_judge_failed() -> None:
    """Valid JSON but no style_distribution → excluded (failed=True)."""
    verdicts = await _judge(_panel('{"reasoning": "no distribution here"}', _GOTHIC, _GOTHIC))
    gem = next(v for v in verdicts if v.judge == "gemini")
    assert gem.failed is True


@pytest.mark.asyncio
async def test_telemetry_callback_fires_once_per_judge() -> None:
    """on_run is invoked exactly once per judge with its success flag."""
    panel = _panel(_GOTHIC, RuntimeError("x"), _MIXED)
    runs = []
    await _judge(panel, on_run=lambda name, model, ms, ok, **kw: runs.append((name, ok)))
    assert len(runs) == 3
    assert sum(1 for _, ok in runs if ok) == 2
    assert ("Panel: OpenAI", False) in runs

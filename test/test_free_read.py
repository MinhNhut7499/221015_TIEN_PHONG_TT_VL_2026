"""Tests for the free-read decorrelation lever (decision C), LLM-free.

Covers the parsing of the free-read JSON, the arbiter-prompt block rendering,
and that ``build_agent7_prompt`` surfaces / omits the block correctly. The
orchestrator's concurrent call itself needs an LLM and is exercised in the eval
run, not here.
"""
from chatbot.services.analysis_orchestrator import _parse_free_read_styles
from chatbot.utils.prompt_builder import (
    _format_free_read,
    build_agent7_prompt,
    build_free_read_prompt,
)
from chatbot.utils.schemas import PipelineInput


def test_parse_free_read_styles_valid_strips_blanks() -> None:
    """Valid JSON yields the style list with blank/non-string entries dropped."""
    out = _parse_free_read_styles('{"styles": ["Byzantine", "Romanesque", "", 3]}')
    assert out == ["Byzantine", "Romanesque"]


def test_parse_free_read_styles_bad_input_returns_empty() -> None:
    """Unparseable or wrong-shaped output yields an empty list (best-effort)."""
    assert _parse_free_read_styles("garbage") == []
    assert _parse_free_read_styles('{"other": 1}') == []


def test_format_free_read_empty_is_blank() -> None:
    """No free-read names → no block at all (backward compatible)."""
    assert _format_free_read([]) == ""
    assert _format_free_read(None) == ""


def test_format_free_read_renders_most_likely_and_alternates() -> None:
    """The block names the most-likely style first, then the alternates."""
    block = _format_free_read(["Mughal", "Moorish", "Indo-Islamic"])
    assert "INDEPENDENT FREE READ" in block
    assert "most likely: Mughal" in block
    assert "Moorish, Indo-Islamic" in block


def test_build_free_read_prompt_asks_for_canonical_json() -> None:
    """The free-read prompt requests a canonical, non-over-refined JSON answer."""
    prompt = build_free_read_prompt()
    assert '"styles"' in prompt
    assert "Revival" in prompt  # explicitly discourages drifting to a Revival twin


def test_agent7_prompt_includes_free_read_when_present() -> None:
    """The arbiter prompt surfaces the free read as an independent opinion."""
    p = build_agent7_prompt([], 0.5, None, ["Mughal"], "", ["Mughal", "Moorish"])
    assert "INDEPENDENT FREE READ" in p
    assert "most likely: Mughal" in p


def test_agent7_prompt_omits_free_read_when_absent() -> None:
    """With no free read, the arbiter prompt is unchanged (no stray block)."""
    p = build_agent7_prompt([], 0.5, None, ["Mughal"], "")
    assert "INDEPENDENT FREE READ" not in p


def test_pipeline_input_carries_free_read_styles() -> None:
    """PipelineInput accepts and defaults the free_read_styles field."""
    assert PipelineInput().free_read_styles == []
    pi = PipelineInput(free_read_styles=["Gothic"])
    assert pi.free_read_styles == ["Gothic"]

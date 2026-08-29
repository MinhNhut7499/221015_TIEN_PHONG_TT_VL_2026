"""Tests for Agent A — evidence extraction (chatbot/services/evidence_extractor.py).

Covers the pure ``parse_evidence_sheet`` (JSON parsing, style_hypotheses ordering,
graceful degradation, no bbox/confidence fields) and the ``MultiEvidenceExtractor``
that runs several extraction calls across providers. LLMs are stubbed.
"""
import io

import pytest
from PIL import Image

from app.config import settings
from chatbot.services.evidence_extractor import (
    MockEvidenceExtractor,
    MultiEvidenceExtractor,
    parse_evidence_sheet,
)
from chatbot.utils.schemas import EvidenceSheet


def _make_jpeg(width: int, height: int) -> bytes:
    """Create a minimal JPEG of the requested size."""
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color=(120, 120, 120)).save(buf, format="JPEG")
    return buf.getvalue()


_VALID_JSON = """```json
{
  "items": [
    {"dimension": "arch", "feature": "pointed arches", "suggested_styles": ["Gothic"], "note": "lancet"},
    {"dimension": "material", "feature": "limestone", "suggested_styles": ["Gothic", "Romanesque"]}
  ],
  "style_hypotheses": ["French Gothic", "Gothic"],
  "proposed_styles": ["Gothic", "Romanesque"],
  "overall_note": "stone church"
}
```"""


class _StubGeminiVision:
    """Stub GeminiService.generate_with_image returning canned text or raising."""

    def __init__(self, raw) -> None:
        self._raw = raw

    async def generate_with_image(self, prompt, image_base64, temperature=0.3) -> str:
        if isinstance(self._raw, Exception):
            raise self._raw
        return self._raw


class _StubOpenAIVision:
    """Stub OpenAIService.chat_structured returning canned text or raising."""

    def __init__(self, raw) -> None:
        self._raw = raw

    async def chat_structured(self, prompt, image_base64=None) -> str:
        if isinstance(self._raw, Exception):
            raise self._raw
        return self._raw


# ── parse_evidence_sheet (pure) ───────────────────────────────────────────────

def test_parse_valid_json_no_bbox_no_confidence() -> None:
    """A valid response yields items with no region/confidence fields."""
    sheet = parse_evidence_sheet(_VALID_JSON)
    assert isinstance(sheet, EvidenceSheet)
    assert len(sheet.items) == 2
    assert sheet.items[0].dimension == "arch"
    assert sheet.overall_note == "stone church"
    assert not hasattr(sheet.items[0], "region")
    assert not hasattr(sheet.items[0], "confidence")


def test_parse_bad_json_degrades_to_empty_sheet() -> None:
    """A non-JSON response degrades to an empty sheet, not an exception."""
    sheet = parse_evidence_sheet("sorry, I cannot help")
    assert isinstance(sheet, EvidenceSheet)
    assert sheet.items == []
    assert sheet.proposed_styles == []


def test_style_hypotheses_lead_proposed_styles() -> None:
    """Building-level style_hypotheses come first in proposed_styles (then cues)."""
    raw = """```json
{
  "items": [
    {"dimension": "arch", "feature": "round arches", "suggested_styles": ["Romanesque"]}
  ],
  "style_hypotheses": ["Spanish Colonial Revival", "Mission Revival"],
  "proposed_styles": []
}
```"""
    sheet = parse_evidence_sheet(raw)
    assert sheet.proposed_styles[0] == "Spanish Colonial Revival"
    assert sheet.proposed_styles[1] == "Mission Revival"
    assert "Romanesque" in sheet.proposed_styles


def test_proposed_styles_dedup_case_insensitive() -> None:
    """proposed_styles merges item suggestions, de-duplicated case-insensitively."""
    raw = """```json
{
  "items": [
    {"dimension": "arch", "feature": "pointed", "suggested_styles": ["Gothic"]},
    {"dimension": "roof", "feature": "spire", "suggested_styles": ["gothic", "French Gothic"]}
  ],
  "proposed_styles": []
}
```"""
    sheet = parse_evidence_sheet(raw)
    assert sheet.proposed_styles == ["Gothic", "French Gothic"]


# ── MultiEvidenceExtractor ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_extract_many_one_sheet_per_successful_call(monkeypatch) -> None:
    """Two providers, both succeed → two sheets."""
    monkeypatch.setattr(settings, "EVIDENCE_EXTRACTION_CALLS", "gemini,openai")
    ex = MultiEvidenceExtractor(
        _StubGeminiVision(_VALID_JSON), _StubOpenAIVision(_VALID_JSON)
    )
    sheets = await ex.extract_many(_make_jpeg(64, 64))
    assert len(sheets) == 2
    assert all(isinstance(s, EvidenceSheet) and s.items for s in sheets)


@pytest.mark.asyncio
async def test_extract_many_falls_back_when_a_provider_fails(monkeypatch) -> None:
    """A failing provider falls back to a working one (A4b) → no sheet lost.

    The OpenAI slot raises, but its fallback chain reaches the working Gemini, so
    both extraction slots still yield a sheet instead of one being dropped.
    """
    monkeypatch.setattr(settings, "EVIDENCE_EXTRACTION_CALLS", "gemini,openai")
    ex = MultiEvidenceExtractor(
        _StubGeminiVision(_VALID_JSON), _StubOpenAIVision(RuntimeError("boom"))
    )
    sheets = await ex.extract_many(_make_jpeg(64, 64))
    assert len(sheets) == 2
    assert all(s.items for s in sheets)


@pytest.mark.asyncio
async def test_extract_many_all_fail_returns_one_empty(monkeypatch) -> None:
    """If every call fails, return a single empty sheet (never crash)."""
    monkeypatch.setattr(settings, "EVIDENCE_EXTRACTION_CALLS", "gemini,openai")
    ex = MultiEvidenceExtractor(
        _StubGeminiVision(RuntimeError("x")), _StubOpenAIVision(RuntimeError("y"))
    )
    sheets = await ex.extract_many(_make_jpeg(64, 64))
    assert len(sheets) == 1
    assert sheets[0].items == []


@pytest.mark.asyncio
async def test_extract_many_reuses_precomputed_base64(monkeypatch) -> None:
    """A supplied image_base64 is reused — the image is NOT re-encoded (encode-once)."""
    monkeypatch.setattr(settings, "EVIDENCE_EXTRACTION_CALLS", "gemini")

    def _boom(_image_bytes):
        raise AssertionError("encode_image_base64 must not be called when b64 is given")

    monkeypatch.setattr(
        "chatbot.services.evidence_extractor.encode_image_base64", _boom
    )
    ex = MultiEvidenceExtractor(
        _StubGeminiVision(_VALID_JSON), _StubOpenAIVision(_VALID_JSON)
    )
    sheets = await ex.extract_many(b"ignored-bytes", image_base64="ZmFrZQ==")
    assert len(sheets) == 1 and sheets[0].items


@pytest.mark.asyncio
async def test_mock_evidence_extractor_returns_sheets() -> None:
    """The mock extractor returns one valid, non-empty sheet via extract_many."""
    sheets = await MockEvidenceExtractor().extract_many(_make_jpeg(100, 100))
    assert len(sheets) == 1
    assert sheets[0].items
    assert "Gothic" in sheets[0].proposed_styles

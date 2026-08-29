"""Tests for the out-of-KB (open-set escape) feature.

Two LLM-free layers:
- ``StyleKbService.cluster_out_of_kb`` — clusters out-of-KB proposed names,
  applies the source-vote threshold, and attaches observed features.
- ``_gate_out_of_kb_primary`` — keeps an out-of-KB primary only when the panel
  clears the higher agreement bar, else demotes it to the best in-KB style.
"""
import pytest

from app.config import settings
from chatbot.services.pipeline_runner import _gate_out_of_kb_primary
from chatbot.services.style_kb_service import get_style_kb
from chatbot.utils.schemas import EvidenceItem, StyleDistribution


@pytest.fixture(scope="module")
def kb():
    """Load the real KB once."""
    return get_style_kb()


# ── cluster_out_of_kb ─────────────────────────────────────────────────────────

def test_cluster_groups_variants_and_thresholds_votes(kb) -> None:
    """Variants of one out-of-KB style cluster into a single ≥min_votes candidate."""
    # "Pueblo Revival" is genuinely absent from the KB; "... style" normalises to
    # the same key, so the two collapse into one cluster.
    proposed = [
        ["Pueblo Revival", "Gothic"],
        ["Pueblo Revival style"],
        ["Brutalism"],  # in-KB → ignored here; also a one-off
    ]
    clusters = kb.cluster_out_of_kb(proposed, min_votes=2)
    names = [c.name for c in clusters]
    assert len(clusters) == 1
    assert clusters[0].votes == 2
    assert "pueblo" in names[0].lower()


def test_cluster_drops_one_off_names(kb) -> None:
    """A name proposed by a single source is below the 2-vote threshold."""
    clusters = kb.cluster_out_of_kb([["Zaha-ism"], ["Gothic"]], min_votes=2)
    assert clusters == []


def test_cluster_attaches_observed_features(kb) -> None:
    """A cluster gets the evidence features whose suggested_styles cite it."""
    items = [
        EvidenceItem(
            dimension="massing",
            feature="earthen adobe terraces",
            suggested_styles=["Pueblo Revival"],
        ),
        EvidenceItem(
            dimension="ornament",
            feature="plain concrete",
            suggested_styles=["Brutalism"],
        ),
    ]
    clusters = kb.cluster_out_of_kb(
        [["Pueblo Revival"], ["Pueblo Revival style"]],
        min_votes=2,
        evidence_items=items,
    )
    assert len(clusters) == 1
    assert "earthen adobe terraces" in clusters[0].features
    assert "plain concrete" not in clusters[0].features  # cited Brutalism, not it


def test_cluster_ignores_in_kb_names(kb) -> None:
    """In-KB names never enter the out-of-KB channel."""
    clusters = kb.cluster_out_of_kb([["Gothic"], ["Gothic"]], min_votes=2)
    assert clusters == []


# ── _gate_out_of_kb_primary ──────────────────────────────────────────────────

def _final(dist: dict) -> dict:
    """Wrap a raw distribution into the arbiter-result dict shape the gate reads."""
    primary = max(dist, key=dist.get)
    return {
        "style": primary,
        "confidence": dist[primary],
        "style_distribution": StyleDistribution(
            distribution=dist, primary=primary, secondary=[]
        ),
        "evidence_per_style": {k: ["x"] for k in dist},
        "key_evidence": ["x"],
        "composition_explanation": "narrative",
    }


def test_gate_keeps_out_of_kb_primary_when_bar_cleared(monkeypatch) -> None:
    """High agreement + 3 judges keeps the out-of-KB style as primary."""
    monkeypatch.setattr(settings, "OUT_OF_KB_AGREEMENT_MIN", 0.7)
    final = _final({"Metabolism": 0.7, "Brutalism": 0.3})
    out, demoted = _gate_out_of_kb_primary(
        final, {"Metabolism"}, valid_judges=3, agreement=0.85,
        allowed={"Metabolism", "Brutalism"}, fallback_primary="Brutalism",
    )
    assert demoted is False
    assert out["style"] == "Metabolism"


def test_gate_demotes_when_agreement_below_bar(monkeypatch) -> None:
    """Low agreement demotes the out-of-KB primary to the best in-KB style."""
    monkeypatch.setattr(settings, "OUT_OF_KB_AGREEMENT_MIN", 0.7)
    final = _final({"Metabolism": 0.7, "Brutalism": 0.3})
    out, demoted = _gate_out_of_kb_primary(
        final, {"Metabolism"}, valid_judges=3, agreement=0.5,
        allowed={"Metabolism", "Brutalism"}, fallback_primary="Brutalism",
    )
    assert demoted is True
    assert out["style"] == "Brutalism"
    assert "Metabolism" not in out["style_distribution"].distribution


def test_gate_demotes_when_too_few_judges(monkeypatch) -> None:
    """Fewer than 3 valid judges demotes the out-of-KB primary regardless of agreement."""
    monkeypatch.setattr(settings, "OUT_OF_KB_AGREEMENT_MIN", 0.7)
    final = _final({"Metabolism": 0.8, "Brutalism": 0.2})
    out, demoted = _gate_out_of_kb_primary(
        final, {"Metabolism"}, valid_judges=2, agreement=0.95,
        allowed={"Metabolism", "Brutalism"}, fallback_primary="Brutalism",
    )
    assert demoted is True
    assert out["style"] == "Brutalism"


def test_gate_noop_for_in_kb_primary() -> None:
    """An in-KB primary is returned unchanged (not gated)."""
    final = _final({"Brutalism": 0.6, "Metabolism": 0.4})
    out, demoted = _gate_out_of_kb_primary(
        final, {"Metabolism"}, valid_judges=1, agreement=None,
        allowed={"Metabolism", "Brutalism"}, fallback_primary="Brutalism",
    )
    assert demoted is False
    assert out is final

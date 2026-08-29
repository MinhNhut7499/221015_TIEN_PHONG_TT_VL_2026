"""Tests for the W1 final-decision logic (DECISION_MODE: arbiter/panel/consensus).

Exercises ``decide_final_distribution`` directly (a pure function) so each mode's
behaviour is locked without running the full LLM pipeline.
"""
from chatbot.services.pipeline_runner import decide_final_distribution
from chatbot.utils.schemas import StyleDistribution

_CANDS = ["Gothic", "Romanesque", "Baroque"]
_ALLOWED = set(_CANDS)
# Three judges that strongly and consistently prefer Gothic (mean margin large).
_PANEL_GOTHIC = [
    {"Gothic": 0.8, "Romanesque": 0.2},
    {"Gothic": 0.7, "Romanesque": 0.3},
    {"Gothic": 0.9, "Romanesque": 0.1},
]
_WEIGHTS = [1.0, 1.0, 1.0]


def _arbiter_baroque() -> dict:
    """Arbiter result whose primary (Baroque) disagrees with the panel (Gothic)."""
    return {
        "style": "Baroque",
        "confidence": 0.9,
        "style_distribution": StyleDistribution(
            distribution={"Baroque": 1.0}, primary="Baroque", secondary=[]
        ),
        "evidence_per_style": {"Baroque": ["solomonic columns"]},
        "key_evidence": ["solomonic columns"],
        "composition_explanation": "baroque reading",
    }


def test_arbiter_mode_returns_arbiter_unchanged() -> None:
    """``arbiter`` mode keeps the arbiter's mixture (baseline behaviour)."""
    arb = _arbiter_baroque()
    out = decide_final_distribution(
        "arbiter", arb, _PANEL_GOTHIC, _WEIGHTS, _CANDS, 1.0, _ALLOWED, "Gothic"
    )
    assert out["style"] == "Baroque"


def test_decision_mode_panel_uses_mean() -> None:
    """``panel`` mode overrides the arbiter with the judges' weighted mean."""
    out = decide_final_distribution(
        "panel", _arbiter_baroque(), _PANEL_GOTHIC, _WEIGHTS, _CANDS, 0.2,
        _ALLOWED, "Gothic",
    )
    assert out["style"] == "Gothic"
    assert out["style_distribution"].primary == "Gothic"
    # Narrative is preserved from the arbiter.
    assert out["composition_explanation"] == "baroque reading"


def test_consensus_keeps_panel_when_agreed() -> None:
    """``consensus``: a decisive, agreeing panel decides (arbiter stays narrator)."""
    out = decide_final_distribution(
        "consensus", _arbiter_baroque(), _PANEL_GOTHIC, _WEIGHTS, _CANDS, 1.0,
        _ALLOWED, "Gothic",
    )
    assert out["style"] == "Gothic"


def test_consensus_arbiter_only_breaks_ties() -> None:
    """``consensus``: a low-agreement panel hands the decision to the arbiter."""
    out = decide_final_distribution(
        "consensus", _arbiter_baroque(), _PANEL_GOTHIC, _WEIGHTS, _CANDS, 0.2,
        _ALLOWED, "Gothic",
    )
    assert out["style"] == "Baroque"


def test_consensus_defers_to_arbiter_on_escape() -> None:
    """``consensus``: an arbiter primary outside the candidate set (escape) wins."""
    arb = _arbiter_baroque()
    arb["style"] = "Moorish"  # not in _CANDS → escape-hatch admission
    arb["style_distribution"] = StyleDistribution(
        distribution={"Moorish": 1.0}, primary="Moorish", secondary=[]
    )
    out = decide_final_distribution(
        "consensus", arb, _PANEL_GOTHIC, _WEIGHTS, _CANDS, 1.0, _ALLOWED, "Gothic"
    )
    assert out["style"] == "Moorish"


def test_panel_mode_falls_back_to_arbiter_without_judges() -> None:
    """With no valid judge distributions, every mode keeps the arbiter result."""
    out = decide_final_distribution(
        "consensus", _arbiter_baroque(), [], [], _CANDS, None, _ALLOWED, "Gothic"
    )
    assert out["style"] == "Baroque"

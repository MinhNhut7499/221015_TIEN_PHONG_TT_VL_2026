"""Tests for inter-judge consensus (chatbot/utils/consensus.py).

Covers mean pairwise Spearman agreement (identical/reversed/degenerate cases),
the guards that return None, and the panel-average fallback distribution.
"""
from chatbot.utils.consensus import mean_distribution, panel_agreement

_INDEX = ["Gothic", "Romanesque", "Baroque"]


def test_agreement_identical_distributions_is_one() -> None:
    """Two judges with the same ranking agree perfectly (ρ = 1.0)."""
    d = {"Gothic": 0.6, "Romanesque": 0.3, "Baroque": 0.1}
    assert panel_agreement([dict(d), dict(d)], _INDEX) == 1.0


def test_agreement_reversed_ranking_is_negative() -> None:
    """Opposite rankings give a negative correlation."""
    d1 = {"Gothic": 0.6, "Romanesque": 0.3, "Baroque": 0.1}
    d2 = {"Gothic": 0.1, "Romanesque": 0.3, "Baroque": 0.6}
    assert panel_agreement([d1, d2], _INDEX) < 0


def test_agreement_three_judges_is_pairwise_mean() -> None:
    """Mean over the 3 pairs: (-1.0 + 0.5 + -0.5) / 3 ≈ -0.333."""
    d1 = {"Gothic": 0.6, "Romanesque": 0.3, "Baroque": 0.1}
    d2 = {"Gothic": 0.1, "Romanesque": 0.3, "Baroque": 0.6}
    d3 = {"Gothic": 0.3, "Romanesque": 0.6, "Baroque": 0.1}
    rho = panel_agreement([d1, d2, d3], _INDEX)
    assert rho is not None
    assert abs(rho - (-1 / 3)) < 1e-3


def test_agreement_single_judge_is_none() -> None:
    """Fewer than two judges → agreement undefined."""
    assert panel_agreement([{"Gothic": 1.0}], _INDEX) is None


def test_agreement_too_few_candidates_is_none() -> None:
    """Fewer than two candidates → rank correlation undefined."""
    assert panel_agreement([{"Gothic": 1.0}, {"Gothic": 1.0}], ["Gothic"]) is None


def test_agreement_skips_degenerate_pair() -> None:
    """A constant (uniform) vector has no rank variance → its pair is skipped.

    With only that one pair, no correlation remains → None.
    """
    uniform = {"Gothic": 1 / 3, "Romanesque": 1 / 3, "Baroque": 1 / 3}
    d = {"Gothic": 0.6, "Romanesque": 0.3, "Baroque": 0.1}
    assert panel_agreement([uniform, d], _INDEX) is None


def test_mean_distribution_averages_and_normalises() -> None:
    """Per-name average over judges, renormalised to sum=1.0."""
    out = mean_distribution(
        [{"Gothic": 1.0}, {"Romanesque": 1.0}], ["Gothic", "Romanesque"]
    )
    assert abs(out["Gothic"] - 0.5) < 1e-9
    assert abs(out["Romanesque"] - 0.5) < 1e-9


def test_mean_distribution_empty_when_no_mass() -> None:
    """No judges (or all-zero) → empty dict."""
    assert mean_distribution([], _INDEX) == {}

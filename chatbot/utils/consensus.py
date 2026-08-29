"""Inter-judge consensus measurement for the open-vocabulary judging panel.

Stage D of the pipeline. Three independent judges (Gemini / DeepSeek / OpenAI)
each score the KB candidates into a probability mixture. We measure how much
they AGREE using the mean pairwise Spearman rank correlation of their score
vectors aligned over a shared candidate index.

Rationale (decision #75): a self-reported confidence is unreliable and the raw
probability magnitudes are not comparable across models (each is "generous" in
its own way), but the RANKING of candidates is comparable. High agreement →
trust the verdict; low agreement → abstain. This replaces self-reported
confidence as the PRIMARY uncertainty signal.
"""
import warnings
from typing import Dict, List, Optional

from scipy.stats import ConstantInputWarning, spearmanr


def _aligned_vector(distribution: Dict[str, float], index: List[str]) -> List[float]:
    """Project a style→prob mapping onto a fixed candidate index (0 for missing)."""
    return [float(distribution.get(name, 0.0)) for name in index]


def panel_agreement(
    distributions: List[Dict[str, float]], index: List[str]
) -> Optional[float]:
    """Return the mean pairwise Spearman correlation across judge distributions.

    Each distribution is aligned over ``index`` (the candidate names) into a
    rank-able score vector. Spearman is computed for every judge pair and the
    results averaged.

    Args:
        distributions: One style→probability mapping per judge (failed judges
            should be excluded by the caller).
        index: The shared candidate-name ordering to align scores on.

    Returns:
        Mean pairwise correlation in [-1.0, 1.0]; ``None`` when it cannot be
        defined — fewer than two judges, fewer than two candidates, or every
        pair degenerate (a judge with a constant/zero vector has no rank
        variance, so that pair's Spearman is NaN and is skipped).
    """
    if len(distributions) < 2 or len(index) < 2:
        return None
    vectors = [_aligned_vector(d, index) for d in distributions]

    correlations: List[float] = []
    with warnings.catch_warnings():
        # A constant (uniform) vector has no rank variance → Spearman is NaN;
        # we skip those pairs deliberately, so silence the expected warning.
        warnings.simplefilter("ignore", ConstantInputWarning)
        for i in range(len(vectors)):
            for j in range(i + 1, len(vectors)):
                rho = spearmanr(vectors[i], vectors[j]).correlation
                if rho == rho:  # skip NaN (a constant/degenerate vector)
                    correlations.append(float(rho))
    if not correlations:
        return None
    return round(sum(correlations) / len(correlations), 4)


def mean_distribution(
    distributions: List[Dict[str, float]], index: List[str]
) -> Dict[str, float]:
    """Average the judges' aligned distributions, renormalised to sum=1.0.

    Used as a fallback final mixture when the arbiter call fails but the panel
    succeeded — a panel average is a better degraded answer than a single-style
    evidence-vote fallback. Returns an empty dict when there is nothing to mix.
    """
    return weighted_mean_distribution(distributions, index, None)


def weighted_mean_distribution(
    distributions: List[Dict[str, float]],
    index: List[str],
    weights: Optional[List[float]] = None,
) -> Dict[str, float]:
    """Weighted average of the judges' aligned distributions, renormalised to 1.0.

    Each judge's distribution is projected onto ``index`` and summed with its
    ``weights`` entry (defaulting to equal weights when ``weights`` is None or
    mismatched). A more decisive / more reliable judge can thus contribute more
    to the panel mixture. Returns an empty dict when there is nothing to mix.
    """
    if not distributions or not index:
        return {}
    if not weights or len(weights) != len(distributions):
        weights = [1.0] * len(distributions)
    totals = {name: 0.0 for name in index}
    for dist, w in zip(distributions, weights):
        for name in index:
            totals[name] += float(dist.get(name, 0.0)) * w
    grand_total = sum(totals.values())
    if grand_total <= 0:
        return {}
    return {name: value / grand_total for name, value in totals.items() if value > 0}

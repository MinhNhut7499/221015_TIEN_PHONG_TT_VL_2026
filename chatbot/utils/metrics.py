"""Calibration + selective-prediction metrics for the learned fuser.

Pure numpy — no sklearn dependency so these can be imported anywhere.
"""
from typing import List, Tuple

import numpy as np


def expected_calibration_error(
    probs: np.ndarray, labels: np.ndarray, n_bins: int = 15
) -> float:
    """Expected Calibration Error over ``n_bins`` equal-width confidence bins.

    ECE = Σ_b (n_b / N) · |accuracy_b − mean_confidence_b|. Lower is better;
    a well-calibrated model is typically < 0.05.

    Args:
        probs: (N, C) predicted probabilities.
        labels: (N,) true class indices.
        n_bins: number of equal-width bins over [0, 1].
    """
    conf = probs.max(axis=1)
    pred = probs.argmax(axis=1)
    correct = (pred == labels).astype(np.float64)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    n = len(labels)
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (conf > lo) & (conf <= hi) if i > 0 else (conf >= lo) & (conf <= hi)
        if mask.any():
            ece += mask.mean() * abs(correct[mask].mean() - conf[mask].mean())
    return float(ece)


def risk_coverage_curve(
    probs: np.ndarray, labels: np.ndarray
) -> List[Tuple[float, float, float]]:
    """Return [(threshold, coverage, selective_accuracy)] sorted by threshold desc.

    At each candidate max-prob threshold τ, coverage = fraction of samples kept
    (max-prob ≥ τ) and selective_accuracy = accuracy on the kept subset.
    """
    conf = probs.max(axis=1)
    pred = probs.argmax(axis=1)
    correct = (pred == labels).astype(np.float64)
    out: List[Tuple[float, float, float]] = []
    for tau in sorted(set(conf.tolist()), reverse=True):
        keep = conf >= tau
        cov = float(keep.mean())
        acc = float(correct[keep].mean()) if keep.any() else 0.0
        out.append((float(tau), cov, acc))
    return out


def pick_threshold(
    probs: np.ndarray, labels: np.ndarray, target_accuracy: float
) -> Tuple[float, float]:
    """Smallest max-prob threshold whose selective accuracy ≥ target.

    Returns ``(threshold, coverage_at_threshold)``. Falls back to the
    highest-coverage point if the target is never reached.
    """
    curve = risk_coverage_curve(probs, labels)
    best = (1.0, 0.0)
    for tau, cov, acc in curve:  # ascending coverage as τ falls
        if acc >= target_accuracy:
            best = (tau, cov)
    return best

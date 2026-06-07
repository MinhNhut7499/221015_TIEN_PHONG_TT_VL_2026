"""Classical CV attribute extractor for the multi-style mixture pipeline.

Seven interpretable visual attributes computed with OpenCV + numpy +
scikit-image. All functions are pure (no I/O beyond the bytes passed in)
and run on CPU in ~150–250 ms for a 256-px image.

The seven attributes feed the ``AttributeVector`` schema, which is then
consumed by:
- Agent 2/5/7 prompts in ``prompt_builder``
- ``compute_attribute_affinity`` in ``rule_checker``
- the global feature evidence stream in ``analysis_orchestrator``

References:
- J. Canny, "A Computational Approach to Edge Detection", PAMI 1986
- P. V. C. Hough, US Patent 3,069,654, 1962
- R. M. Haralick et al., "Textural Features for Image Classification",
  IEEE Trans. SMC, 1973
"""
import io
import math
from typing import Tuple

import cv2
import numpy as np
from PIL import Image
from skimage.feature import graycomatrix, graycoprops

from chatbot.utils.schemas import AttributeVector


DEFAULT_RESIZE = 256
"""Target longest side for all attribute computations.

Bounds compute cost and keeps Hough/Canny thresholds stable across input
resolutions.
"""

_LINE_ANGLE_TOL_DEG = 15.0
"""Tolerance for classifying a Hough line as vertical or horizontal."""

_N_ORIENTATION_BINS = 18
"""Bin count for edge_orientation_entropy (10° per bin)."""


def _load_grayscale(image_bytes: bytes, resize_to: int = DEFAULT_RESIZE) -> np.ndarray:
    """Decode image bytes and return a uint8 grayscale array.

    The image is resized so its longest side equals ``resize_to`` while
    preserving aspect ratio. Smaller images are left unchanged.
    """
    img = Image.open(io.BytesIO(image_bytes)).convert("L")
    w, h = img.size
    scale = resize_to / max(w, h)
    if scale < 1.0:
        new_size = (max(1, int(round(w * scale))), max(1, int(round(h * scale))))
        img = img.resize(new_size, Image.BILINEAR)
    return np.asarray(img, dtype=np.uint8)


# ── Attribute 1: symmetry ─────────────────────────────────────────────────────

def compute_symmetry(gray: np.ndarray) -> float:
    """Horizontal mirror symmetry via normalised cross-correlation.

    The image is split at its vertical centre; the right half is mirrored
    and aligned with the left half, then NCC between the two is returned.
    High values are characteristic of Neoclassical, Renaissance, Art Deco;
    low values of Deconstructivism / High-tech.

    Returns:
        Value clipped to ``[0.0, 1.0]``.
    """
    h, w = gray.shape
    half = w // 2
    if half <= 0:
        return 0.0
    left = gray[:, :half].astype(np.float32)
    right = gray[:, w - half : w].astype(np.float32)
    right_mirrored = right[:, ::-1]

    l_centered = left - left.mean()
    r_centered = right_mirrored - right_mirrored.mean()

    numerator = float((l_centered * r_centered).sum())
    denominator = float(
        math.sqrt((l_centered ** 2).sum() * (r_centered ** 2).sum())
    )
    if denominator <= 1e-9:
        return 0.0
    return max(0.0, min(1.0, numerator / denominator))


# ── Attributes 2 & 3: line dominance ──────────────────────────────────────────

def compute_line_dominance(gray: np.ndarray) -> Tuple[float, float]:
    """Vertical and horizontal line dominance via probabilistic Hough.

    Canny edges → ``cv2.HoughLinesP`` → segments are classified vertical
    (within ±15° of 90°), horizontal (within ±15° of 0°), or other. Each
    category's total length is divided by the total length of all detected
    segments.

    Returns:
        ``(vertical_dominance, horizontal_dominance)``, each in ``[0.0, 1.0]``.
        The two values do not sum to 1 — diagonal lines are excluded.
    """
    edges = cv2.Canny(gray, threshold1=50, threshold2=150, apertureSize=3)
    h, w = gray.shape
    min_len = max(10, int(0.05 * max(h, w)))
    segments = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180.0,
        threshold=40,
        minLineLength=min_len,
        maxLineGap=10,
    )
    if segments is None or len(segments) == 0:
        return 0.0, 0.0

    v_len = 0.0
    h_len = 0.0
    total_len = 0.0
    for seg in segments[:, 0, :]:
        x1, y1, x2, y2 = seg
        dx = float(x2 - x1)
        dy = float(y2 - y1)
        length = math.hypot(dx, dy)
        if length <= 0:
            continue
        total_len += length
        # Angle from horizontal axis, folded to [0, 90]
        angle_deg = math.degrees(math.atan2(abs(dy), abs(dx)))
        if angle_deg >= 90.0 - _LINE_ANGLE_TOL_DEG:
            v_len += length
        elif angle_deg <= _LINE_ANGLE_TOL_DEG:
            h_len += length

    if total_len <= 0:
        return 0.0, 0.0
    return v_len / total_len, h_len / total_len


# ── Attribute 4: curvature ────────────────────────────────────────────────────

def compute_curvature(gray: np.ndarray) -> float:
    """Proportion of curved structure in the image.

    Combines two signals:
    1. ``cv2.HoughCircles`` — explicit detection of arches / domes / rose
       windows.
    2. Contour straight-vs-curved ratio — for each significant contour,
       compare its raw arc length to the arc length of its polygonal
       approximation; values >1.05 are tallied as curved.

    Returns:
        Value in ``[0.0, 1.0]``. High for Baroque, Art Nouveau and Gothic;
        low for Modernism, Brutalism, Deconstructivism.
    """
    h, w = gray.shape
    blurred = cv2.GaussianBlur(gray, (5, 5), 1.0)

    circles = cv2.HoughCircles(
        blurred,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=max(20, w // 16),
        param1=120,
        param2=40,
        minRadius=max(5, w // 50),
        maxRadius=max(20, w // 4),
    )
    circle_count = 0 if circles is None else int(circles.shape[1])
    # One detected circle per ~20 000 px is a strong curvature signal.
    circle_signal = min(1.0, circle_count / max(1.0, (h * w) / 20000.0))

    edges = cv2.Canny(blurred, 50, 150)
    contours, _ = cv2.findContours(
        edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE
    )
    curved = 0
    counted = 0
    for cnt in contours:
        if len(cnt) < 20:
            continue
        perimeter = cv2.arcLength(cnt, closed=True)
        if perimeter <= 0:
            continue
        approx = cv2.approxPolyDP(cnt, epsilon=0.01 * perimeter, closed=True)
        approx_perimeter = cv2.arcLength(approx, closed=True)
        if approx_perimeter <= 0:
            continue
        if perimeter / approx_perimeter > 1.05:
            curved += 1
        counted += 1
    contour_signal = (curved / counted) if counted > 0 else 0.0

    return float(min(1.0, 0.5 * contour_signal + 0.5 * circle_signal))


# ── Attribute 5: surface roughness via GLCM contrast ──────────────────────────

def compute_surface_roughness(gray: np.ndarray) -> float:
    """GLCM contrast (Haralick 1973) as a proxy for surface roughness.

    Computes the gray-level co-occurrence matrix at four orientations and
    two distances, then averages the contrast property. Smooth glass /
    polished concrete give low contrast; raw concrete, brickwork and
    rough stone give high contrast.

    Returns:
        Value squashed to ``[0.0, 1.0]`` via ``1 - exp(-contrast / 20)``.
    """
    quantised = (gray // 16).astype(np.uint8)  # 16 levels
    glcm = graycomatrix(
        quantised,
        distances=[1, 2],
        angles=[0.0, math.pi / 4.0, math.pi / 2.0, 3.0 * math.pi / 4.0],
        levels=16,
        symmetric=True,
        normed=True,
    )
    contrast = float(graycoprops(glcm, "contrast").mean())
    return float(1.0 - math.exp(-contrast / 20.0))


# ── Attribute 6: edge density ─────────────────────────────────────────────────

def compute_edge_density(gray: np.ndarray) -> float:
    """Multi-scale Canny edge density — proxy for ornamentation amount.

    Computes the ratio of edge pixels to total pixels at full and half
    resolution and averages them. The raw value is squashed by dividing
    by 0.25 (empirical headroom — natural facades rarely exceed this)
    and clipped to 1.0.

    Returns:
        Value in ``[0.0, 1.0]``. Low for clean modernist facades; high
        for ornate Baroque / Art Nouveau elevations.
    """
    edges_full = cv2.Canny(gray, 60, 160)
    density_full = float(edges_full.sum() / 255.0) / float(edges_full.size)

    h, w = gray.shape
    half = cv2.resize(
        gray,
        (max(1, w // 2), max(1, h // 2)),
        interpolation=cv2.INTER_AREA,
    )
    edges_half = cv2.Canny(half, 60, 160)
    density_half = float(edges_half.sum() / 255.0) / float(edges_half.size)

    raw = 0.5 * (density_full + density_half)
    return float(min(1.0, raw / 0.25))


# ── Attribute 7: edge orientation entropy ─────────────────────────────────────

def compute_edge_orientation_entropy(gray: np.ndarray) -> float:
    """Shannon entropy of the gradient orientation histogram.

    Sobel gradients give per-pixel orientation; only pixels with gradient
    magnitude above ``mean + std`` contribute to the histogram. Orientations
    are folded to ``[0, 180)`` since edges are undirected, then binned into
    18 bins of 10° each.

    Low entropy → orientations cluster (geometric ornament of Art Deco).
    High entropy → orientations spread uniformly (organic curves of Art
    Nouveau).

    Returns:
        Entropy in ``[0.0, log(18)] ≈ [0.0, 2.89]``.
    """
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = np.sqrt(gx * gx + gy * gy)
    threshold = float(magnitude.mean() + magnitude.std())
    mask = magnitude > threshold
    if not mask.any():
        return 0.0
    angles = (np.degrees(np.arctan2(gy[mask], gx[mask])) + 180.0) % 180.0
    hist, _ = np.histogram(angles, bins=_N_ORIENTATION_BINS, range=(0.0, 180.0))
    probs = hist.astype(np.float64) / float(hist.sum())
    probs = probs[probs > 0]
    return float(-(probs * np.log(probs)).sum())


# ── Aggregator ────────────────────────────────────────────────────────────────

def extract_attributes(image_bytes: bytes) -> AttributeVector:
    """Run all seven extractors and return the populated AttributeVector.

    The image is decoded and resized once; each extractor then runs on the
    shared grayscale array.
    """
    gray = _load_grayscale(image_bytes)
    vertical, horizontal = compute_line_dominance(gray)
    return AttributeVector(
        symmetry_score=compute_symmetry(gray),
        vertical_dominance=vertical,
        horizontal_dominance=horizontal,
        curvature_score=compute_curvature(gray),
        surface_roughness=compute_surface_roughness(gray),
        edge_density=compute_edge_density(gray),
        edge_orientation_entropy=compute_edge_orientation_entropy(gray),
    )

"""Unit tests for chatbot/utils/cv_attributes.py.

Uses synthetic numpy images (via PIL → bytes) so the tests cover both the
public ``extract_attributes(bytes)`` entry point and the individual
per-attribute functions that operate on grayscale arrays.

Run with:
    pytest test/test_cv_attributes.py -v
"""
import io
import math

import numpy as np
import pytest
from PIL import Image

from chatbot.utils.cv_attributes import (
    _N_ORIENTATION_BINS,
    compute_curvature,
    compute_edge_density,
    compute_edge_orientation_entropy,
    compute_line_dominance,
    compute_surface_roughness,
    compute_symmetry,
    extract_attributes,
)
from chatbot.utils.schemas import AttributeVector


# ── Helpers ───────────────────────────────────────────────────────────────────

def _to_bytes(arr: np.ndarray) -> bytes:
    """Encode a uint8 grayscale array to PNG bytes."""
    buf = io.BytesIO()
    Image.fromarray(arr, mode="L").save(buf, format="PNG")
    return buf.getvalue()


def _vertical_stripes(h: int = 200, w: int = 200, stripe_width: int = 10) -> np.ndarray:
    """Image with alternating vertical black/white stripes."""
    img = np.zeros((h, w), dtype=np.uint8)
    for x in range(0, w, stripe_width * 2):
        img[:, x : x + stripe_width] = 255
    return img


def _horizontal_stripes(h: int = 200, w: int = 200, stripe_height: int = 10) -> np.ndarray:
    """Image with alternating horizontal black/white stripes."""
    img = np.zeros((h, w), dtype=np.uint8)
    for y in range(0, h, stripe_height * 2):
        img[y : y + stripe_height, :] = 255
    return img


def _symmetric_pattern(h: int = 200, w: int = 200) -> np.ndarray:
    """A horizontally mirror-symmetric shape on a black background."""
    img = np.zeros((h, w), dtype=np.uint8)
    # Triangle centred on x = w/2
    cy, cx = h // 2, w // 2
    for y in range(h):
        spread = int(0.4 * h - abs(y - cy) * 0.6)
        if spread <= 0:
            continue
        img[y, cx - spread : cx + spread] = 200
    return img


def _grid_pattern(h: int = 200, w: int = 200, cell: int = 20) -> np.ndarray:
    """A black-on-white grid — only vertical + horizontal orientations."""
    img = np.full((h, w), 255, dtype=np.uint8)
    for x in range(0, w, cell):
        img[:, x : x + 1] = 0
    for y in range(0, h, cell):
        img[y : y + 1, :] = 0
    return img


def _isotropic_noise(h: int = 200, w: int = 200, seed: int = 0) -> np.ndarray:
    """Random noise — gradient orientations should be roughly uniform."""
    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, size=(h, w), dtype=np.uint8)


# ── compute_symmetry ──────────────────────────────────────────────────────────

def test_symmetry_high_for_mirror_symmetric_image() -> None:
    """A mirror-symmetric triangle should score above 0.9."""
    img = _symmetric_pattern()
    assert compute_symmetry(img) > 0.9


def test_symmetry_low_for_asymmetric_image() -> None:
    """Two disjoint blobs on different halves should score low."""
    img = np.zeros((200, 200), dtype=np.uint8)
    img[50:80, 20:60] = 255  # left blob
    img[120:170, 130:190] = 255  # right blob (different position + size)
    score = compute_symmetry(img)
    assert score < 0.5


def test_symmetry_handles_uniform_image() -> None:
    """A uniform image has zero variance — should return 0.0 (not NaN)."""
    img = np.full((100, 100), 128, dtype=np.uint8)
    assert compute_symmetry(img) == 0.0


# ── compute_line_dominance ────────────────────────────────────────────────────

def test_vertical_stripes_score_vertical_dominance() -> None:
    """Vertical stripes → vertical_dominance >> horizontal_dominance."""
    img = _vertical_stripes()
    vertical, horizontal = compute_line_dominance(img)
    assert vertical > 0.5
    assert vertical > horizontal


def test_horizontal_stripes_score_horizontal_dominance() -> None:
    """Horizontal stripes → horizontal_dominance >> vertical_dominance."""
    img = _horizontal_stripes()
    vertical, horizontal = compute_line_dominance(img)
    assert horizontal > 0.5
    assert horizontal > vertical


def test_uniform_image_has_zero_line_dominance() -> None:
    """A blank image has no detectable lines — both ratios should be 0.0."""
    img = np.full((200, 200), 128, dtype=np.uint8)
    vertical, horizontal = compute_line_dominance(img)
    assert vertical == 0.0
    assert horizontal == 0.0


# ── compute_curvature ─────────────────────────────────────────────────────────

def test_curvature_low_for_pure_rectangles() -> None:
    """Vertical stripes are entirely straight — curvature should be low."""
    img = _vertical_stripes()
    assert compute_curvature(img) < 0.4


def test_curvature_high_for_circle() -> None:
    """A filled white circle on black should produce a non-zero curvature."""
    h = w = 200
    img = np.zeros((h, w), dtype=np.uint8)
    yy, xx = np.ogrid[:h, :w]
    mask = (xx - w // 2) ** 2 + (yy - h // 2) ** 2 <= 60 ** 2
    img[mask] = 230
    assert compute_curvature(img) > 0.0


# ── compute_surface_roughness ─────────────────────────────────────────────────

def test_surface_roughness_low_for_uniform_image() -> None:
    """A uniform-gray image has zero contrast → roughness ≈ 0."""
    img = np.full((100, 100), 128, dtype=np.uint8)
    assert compute_surface_roughness(img) < 0.05


def test_surface_roughness_higher_for_noise_than_uniform() -> None:
    """Isotropic noise has much higher GLCM contrast than a uniform image."""
    smooth = np.full((150, 150), 128, dtype=np.uint8)
    rough = _isotropic_noise(150, 150, seed=42)
    assert compute_surface_roughness(rough) > compute_surface_roughness(smooth) + 0.5


# ── compute_edge_density ──────────────────────────────────────────────────────

def test_edge_density_zero_for_uniform_image() -> None:
    """A uniform image has no Canny edges."""
    img = np.full((100, 100), 128, dtype=np.uint8)
    assert compute_edge_density(img) == 0.0


def test_edge_density_higher_for_grid_than_uniform() -> None:
    """A dense grid produces many edges; uniform produces none."""
    grid = _grid_pattern(cell=10)
    blank = np.full((200, 200), 128, dtype=np.uint8)
    assert compute_edge_density(grid) > compute_edge_density(blank) + 0.2


# ── compute_edge_orientation_entropy ──────────────────────────────────────────

def test_grid_pattern_has_low_orientation_entropy() -> None:
    """A grid has only horizontal + vertical gradients → low entropy."""
    img = _grid_pattern()
    entropy = compute_edge_orientation_entropy(img)
    # log(18) ≈ 2.89; geometric grid should be well below the midpoint.
    assert entropy < 1.5


def test_random_noise_has_high_orientation_entropy() -> None:
    """Random noise spreads orientations uniformly → entropy near log(18)."""
    img = _isotropic_noise(200, 200, seed=7)
    entropy = compute_edge_orientation_entropy(img)
    assert entropy > 0.8 * math.log(_N_ORIENTATION_BINS)


# ── extract_attributes (aggregator) ───────────────────────────────────────────

def test_extract_attributes_returns_attribute_vector() -> None:
    """The public entry point returns a validated AttributeVector."""
    img = _symmetric_pattern()
    result = extract_attributes(_to_bytes(img))
    assert isinstance(result, AttributeVector)
    # All ratio fields in [0, 1]
    for field in (
        "symmetry_score",
        "vertical_dominance",
        "horizontal_dominance",
        "curvature_score",
        "surface_roughness",
        "edge_density",
    ):
        value = getattr(result, field)
        assert 0.0 <= value <= 1.0, f"{field}={value} out of [0,1]"
    # Entropy upper bound is log(N_BINS)
    assert 0.0 <= result.edge_orientation_entropy <= math.log(_N_ORIENTATION_BINS) + 1e-6


def test_extract_attributes_is_deterministic() -> None:
    """Same image bytes → same AttributeVector."""
    img_bytes = _to_bytes(_grid_pattern())
    first = extract_attributes(img_bytes)
    second = extract_attributes(img_bytes)
    assert first.model_dump() == second.model_dump()

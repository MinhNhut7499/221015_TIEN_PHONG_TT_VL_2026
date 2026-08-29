"""Tests for encode_image_base64 — EXIF orientation + downscale (latency lever).

The vision calls all carry the image, so encode_image_base64 is the single
chokepoint that (optionally) applies the EXIF orientation and downscales the
image before it is sent. These tests pin the safe behaviour: only shrink (never
upscale), preserve aspect ratio, honour the disable flags, and rotate per EXIF.
"""
import base64
import io

from PIL import Image

from app.config import settings
from chatbot.utils.image_utils import encode_image_base64


def _jpeg(width: int, height: int, exif_orientation: int = None) -> bytes:
    """Create a JPEG of the given size, optionally with an EXIF orientation tag."""
    img = Image.new("RGB", (width, height), color=(120, 120, 120))
    buf = io.BytesIO()
    if exif_orientation is not None:
        exif = img.getexif()
        exif[274] = exif_orientation  # 274 = Orientation
        img.save(buf, format="JPEG", exif=exif)
    else:
        img.save(buf, format="JPEG")
    return buf.getvalue()


def _decoded_size(b64: str) -> tuple:
    """Decode a base64 JPEG string and return its (width, height)."""
    return Image.open(io.BytesIO(base64.b64decode(b64))).size


def test_downscale_caps_long_edge(monkeypatch) -> None:
    """An image larger than the cap is shrunk so its long edge == the cap."""
    monkeypatch.setattr(settings, "VISION_IMAGE_MAX_DIM", 1536)
    monkeypatch.setattr(settings, "APPLY_EXIF_TRANSPOSE", False)
    w, h = _decoded_size(encode_image_base64(_jpeg(4000, 3000)))
    assert max(w, h) == 1536
    # aspect ratio preserved (4:3)
    assert round(w / h, 2) == round(4000 / 3000, 2)


def test_no_upscale_of_small_image(monkeypatch) -> None:
    """An image smaller than the cap is left at its original size (never upscaled)."""
    monkeypatch.setattr(settings, "VISION_IMAGE_MAX_DIM", 1536)
    monkeypatch.setattr(settings, "APPLY_EXIF_TRANSPOSE", False)
    assert _decoded_size(encode_image_base64(_jpeg(800, 600))) == (800, 600)


def test_max_dim_zero_keeps_resolution(monkeypatch) -> None:
    """VISION_IMAGE_MAX_DIM=0 disables resizing → original resolution (rollback)."""
    monkeypatch.setattr(settings, "VISION_IMAGE_MAX_DIM", 0)
    monkeypatch.setattr(settings, "APPLY_EXIF_TRANSPOSE", False)
    assert _decoded_size(encode_image_base64(_jpeg(2000, 1000))) == (2000, 1000)


def test_exif_transpose_rotates(monkeypatch) -> None:
    """Orientation 6 (rotate 90°) swaps a 100x200 image to 200x100 when enabled."""
    monkeypatch.setattr(settings, "VISION_IMAGE_MAX_DIM", 0)
    monkeypatch.setattr(settings, "APPLY_EXIF_TRANSPOSE", True)
    assert _decoded_size(encode_image_base64(_jpeg(100, 200, exif_orientation=6))) == (200, 100)


def test_exif_transpose_disabled_keeps_orientation(monkeypatch) -> None:
    """With APPLY_EXIF_TRANSPOSE off the pixels are left unrotated (legacy)."""
    monkeypatch.setattr(settings, "VISION_IMAGE_MAX_DIM", 0)
    monkeypatch.setattr(settings, "APPLY_EXIF_TRANSPOSE", False)
    assert _decoded_size(encode_image_base64(_jpeg(100, 200, exif_orientation=6))) == (100, 200)

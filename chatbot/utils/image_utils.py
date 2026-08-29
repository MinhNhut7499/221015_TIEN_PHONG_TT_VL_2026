"""Image utility helpers for the analysis pipeline.

Handles base64 encoding and component cropping using Pillow.
All functions are pure (no side effects, no I/O beyond the bytes passed in).
"""
import base64
import io
import logging

from PIL import Image, ImageOps

from app.config import settings
from chatbot.utils.schemas import BoundingBox

logger = logging.getLogger(__name__)

# Aspect ratio above which capping the long edge over-shrinks the short edge
# (e.g. a panorama) — log a warning so detail loss is visible in monitoring.
_PANORAMA_RATIO = 3.0


def encode_image_base64(image_bytes: bytes) -> str:
    """Encode raw image bytes to a base64 JPEG string.

    Converts any supported format (PNG, WEBP, …) to JPEG before encoding so
    downstream LLM calls always receive JPEG regardless of upload format. When
    ``settings.APPLY_EXIF_TRANSPOSE`` is set the EXIF orientation is applied first
    (rotated phone photos are sent upright). When ``settings.VISION_IMAGE_MAX_DIM``
    is > 0 the image is downscaled so its long edge is at most that many pixels
    (only ever shrunk, never upscaled) — every vision call carries the image, so
    shrinking once here cuts payload + vision tokens across the whole pipeline.

    Args:
        image_bytes: Raw bytes of the original uploaded image.

    Returns:
        Base64-encoded JPEG string (no data-URI prefix).
    """
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    if settings.APPLY_EXIF_TRANSPOSE:
        img = ImageOps.exif_transpose(img)

    max_dim = settings.VISION_IMAGE_MAX_DIM
    if max_dim and max(img.size) > max_dim:
        width, height = img.size
        if max(width, height) / max(1, min(width, height)) > _PANORAMA_RATIO:
            logger.warning(
                "Extreme aspect ratio %dx%d — capping the long edge to %dpx leaves "
                "the short edge small (detail loss); consider an area-based cap.",
                width, height, max_dim,
            )
        # thumbnail() preserves aspect ratio and only shrinks (never upscales).
        img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=85)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def crop_component(image_bytes: bytes, bbox: BoundingBox) -> str:
    """Crop a component region from the image and return it as a base64 JPEG.

    Args:
        image_bytes: Raw bytes of the original uploaded image.
        bbox: Bounding box of the component to crop.

    Returns:
        Base64-encoded JPEG string of the cropped region.
    """
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    width, height = img.size
    x_min = max(0, bbox.x_min)
    y_min = max(0, bbox.y_min)
    x_max = min(width, bbox.x_max)
    y_max = min(height, bbox.y_max)
    cropped = img.crop((x_min, y_min, x_max, y_max))
    buffer = io.BytesIO()
    cropped.save(buffer, format="JPEG", quality=85)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")

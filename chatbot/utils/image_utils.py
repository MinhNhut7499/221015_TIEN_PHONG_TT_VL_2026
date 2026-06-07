"""Image utility helpers for the analysis pipeline.

Handles base64 encoding and component cropping using Pillow.
All functions are pure (no side effects, no I/O beyond the bytes passed in).
"""
import base64
import io

from PIL import Image

from chatbot.utils.schemas import BoundingBox


def encode_image_base64(image_bytes: bytes) -> str:
    """Encode raw image bytes to a base64 JPEG string.

    Converts any supported format (PNG, WEBP, …) to JPEG before encoding
    so downstream LLM calls always receive JPEG regardless of upload format.

    Args:
        image_bytes: Raw bytes of the original uploaded image.

    Returns:
        Base64-encoded JPEG string (no data-URI prefix).
    """
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
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

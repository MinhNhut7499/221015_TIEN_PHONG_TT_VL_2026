"""Shared builder for a stored analysis detail payload.

Both the user-scoped endpoint (``GET /analyze/history/{id}``) and the admin
endpoint (``GET /admin/images/{id}``) return the same shape: the full
``AnalyzeResponse`` JSON stored in ``BuildingStyleResults.DetailJson`` when
present, or a summary reconstructed from the persisted verdict columns for
analyses created before full-result persistence existed.
"""
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from app.models.orm_models import BuildingStyleResult, Image

logger = logging.getLogger(__name__)


def build_detail_payload(
    image_id: str, img: Image, bsr: Optional[BuildingStyleResult]
) -> Dict[str, Any]:
    """Return the full stored analysis for an image (DetailJson or summary).

    Args:
        image_id: The canonical Images.ImageId (authoritative; the row was
            looked up by it).
        img: The Image row (supplies ``ImagePath`` → ``file_id``).
        bsr: The associated BuildingStyleResult, if any.

    Returns:
        An AnalyzeResponse-shaped dict. Always carries ``image_id`` and
        ``file_id`` so the frontend can fetch the original image.
    """
    file_id = Path(img.ImagePath).stem if img.ImagePath else None

    if bsr is not None and bsr.DetailJson:
        try:
            detail: Dict[str, Any] = json.loads(bsr.DetailJson)
            detail["image_id"] = image_id
            detail["file_id"] = file_id
            return detail
        except (ValueError, TypeError):
            logger.warning(
                "Corrupt DetailJson for image %s; falling back to summary",
                image_id,
            )

    # Summary fallback (old analyses without DetailJson).
    return {
        "image_id": image_id,
        "file_id": file_id,
        "style": bsr.FinalStyle if bsr else None,
        "confidence": bsr.Confidence if bsr else None,
        "explanation": (bsr.Explanation if bsr else "") or "",
        "key_evidence": (bsr.KeyEvidence.split("\n") if bsr and bsr.KeyEvidence else []),
        "components": [],
        "processing_time_ms": 0.0,
    }

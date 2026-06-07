"""RealYOLOService: YOLOv8s component detector backed by a trained best.pt.

Drop-in replacement for ``MockYOLOService`` — same ``detect(image_bytes)``
signature returning ``List[DetectedComponent]``. The Ultralytics model is
loaded lazily on the first ``detect`` call so importing this module (or
constructing the service) never touches the filesystem or allocates the
network until a request actually arrives.

Detected boxes whose class label is not one of the 11 finalized
``ComponentType`` values are dropped — fail-safe at the YOLO ↔ pipeline
contract boundary (see decision #4 in CLAUDE.md).
"""
import io
import logging
import uuid
from typing import List, Optional

import numpy as np
from PIL import Image
from ultralytics import YOLO

from app.config import settings
from chatbot.utils.image_utils import crop_component, encode_image_base64
from chatbot.utils.schemas import (
    COMPONENT_TYPES,
    BoundingBox,
    ComponentType,
    DetectedComponent,
)

logger = logging.getLogger(__name__)

_VALID_TYPES = set(COMPONENT_TYPES)


class RealYOLOService:
    """YOLOv8s detector that returns DetectedComponent objects for an image.

    Args:
        model_path: Path to the trained YOLOv8s detection .pt file (best.pt).
        conf_threshold: Minimum detection confidence to keep a box.
    """

    def __init__(self, model_path: str, conf_threshold: Optional[float] = None) -> None:
        """Store the model path and threshold; defer loading until first use."""
        self._model_path = model_path
        self._conf_threshold = (
            conf_threshold
            if conf_threshold is not None
            else settings.YOLO_CONF_THRESHOLD
        )
        self._model = None  # Lazy-loaded Ultralytics YOLO instance.

    def _ensure_model(self) -> None:
        """Load the Ultralytics YOLO model on first use."""
        if self._model is None:
            logger.info("Loading YOLO detection model from %s", self._model_path)
            self._model = YOLO(self._model_path)

    def detect(self, image_bytes: bytes) -> List[DetectedComponent]:
        """Detect architectural components in the image.

        Args:
            image_bytes: Raw bytes of the uploaded image.

        Returns:
            List of DetectedComponent (one per kept box). Boxes below the
            confidence threshold or with an unknown class label are dropped;
            an empty list is a valid result when nothing is detected.
        """
        self._ensure_model()
        full_b64 = encode_image_base64(image_bytes)
        results = self._model.predict(  # type: ignore[union-attr]
            source=self._decode_image(image_bytes),
            conf=self._conf_threshold,
            verbose=False,
        )

        components: List[DetectedComponent] = []
        for result in results:
            names = result.names
            boxes = result.boxes
            if boxes is None:
                continue
            for box in boxes:
                label = self._normalise_label(names[int(box.cls[0])])
                if label not in _VALID_TYPES:
                    logger.debug("Dropping out-of-contract YOLO label: %s", label)
                    continue
                xyxy = box.xyxy[0].tolist()
                bbox = BoundingBox(
                    x_min=int(xyxy[0]),
                    y_min=int(xyxy[1]),
                    x_max=int(xyxy[2]),
                    y_max=int(xyxy[3]),
                )
                components.append(
                    DetectedComponent(
                        component_id=self._box_id(result, box),
                        component_type=label,  # type: ignore[arg-type]
                        detection_confidence=round(float(box.conf[0]), 3),
                        bounding_box=bbox,
                        crop_base64=crop_component(image_bytes, bbox),
                        full_image_base64=full_b64,
                    )
                )
        return components

    @staticmethod
    def _decode_image(image_bytes: bytes) -> "np.ndarray":
        """Decode raw bytes to an RGB numpy array for Ultralytics inference."""
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        return np.array(img)

    @staticmethod
    def _normalise_label(label: str) -> str:
        """Normalise a YOLO class name to the snake_case ComponentType form."""
        return label.strip().lower().replace(" ", "_").replace("-", "_")

    @staticmethod
    def _box_id(result, box) -> str:
        """Return a stable per-box id (Ultralytics track id if present, else uuid)."""
        if getattr(box, "id", None) is not None:
            return f"yolo-{int(box.id[0])}"
        return str(uuid.uuid4())

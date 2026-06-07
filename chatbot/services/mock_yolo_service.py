"""MockYOLOService: deterministic fake YOLO detector for development.

Produces a reproducible set of DetectedComponent objects seeded from
the MD5 hash of the image bytes — the same image always returns the same
components, making pipeline output predictable during testing.

Replace with RealYOLOService once the model is trained:
    class RealYOLOService:
        def detect(self, image_bytes: bytes) -> List[DetectedComponent]: ...
No changes to pipeline_runner.py are needed when swapping.
"""
import hashlib
import random
import uuid
from typing import List

from chatbot.utils.image_utils import encode_image_base64
from chatbot.utils.schemas import BoundingBox, ComponentType, DetectedComponent

_COMPONENT_TYPES: List[ComponentType] = [  # type: ignore[assignment]
    "arch",
    "spire",
    "dome",
    "pediment",
    "column_capital",
    "solomonic_column",
    "curved_iron_balcony",
    "flat_roof",
]


class MockYOLOService:
    """Fake YOLO service that returns deterministic components for development.

    The same image bytes always produce the same number and types of components,
    ensuring reproducible pipeline runs without a trained model.
    """

    def detect(self, image_bytes: bytes) -> List[DetectedComponent]:
        """Return a deterministic list of detected components.

        Args:
            image_bytes: Raw image bytes (used only for seeding the RNG).

        Returns:
            List of 3–6 DetectedComponent objects with plausible bboxes and
            confidence scores in [0.60, 0.95].
        """
        seed = hashlib.md5(image_bytes).hexdigest()
        rng = random.Random(seed)
        full_b64 = encode_image_base64(image_bytes)
        n = rng.randint(3, 6)
        selected_types: List[ComponentType] = rng.sample(  # type: ignore[assignment]
            _COMPONENT_TYPES, min(n, len(_COMPONENT_TYPES))
        )
        components: List[DetectedComponent] = []
        for ctype in selected_types:
            bbox = _random_bbox(rng)
            components.append(
                DetectedComponent(
                    component_id=str(uuid.uuid4()),
                    component_type=ctype,
                    detection_confidence=round(rng.uniform(0.60, 0.95), 3),
                    bounding_box=bbox,
                    crop_base64=full_b64,
                    full_image_base64=full_b64,
                )
            )
        return components


def _random_bbox(rng: random.Random) -> BoundingBox:
    """Generate a plausible random bounding box within a 1000×1000 image grid."""
    x_min = rng.randint(0, 600)
    y_min = rng.randint(0, 600)
    x_max = x_min + rng.randint(100, 350)
    y_max = y_min + rng.randint(100, 350)
    return BoundingBox(x_min=x_min, y_min=y_min, x_max=x_max, y_max=y_max)

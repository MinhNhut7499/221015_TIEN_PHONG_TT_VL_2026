"""MockGlobalFeatureService: deterministic fake global feature extractor for development.

Returns a reproducible ``GlobalFeatureOutput`` whose ``style_prior`` is seeded
from the MD5 of the image bytes (so the same image always produces the same
prior) and whose ``attributes`` are the REAL output of
``chatbot.utils.cv_attributes.extract_attributes`` — i.e. the geometric and
textural features are genuine even before the ResNet50 head is trained. The
``gradcam_b64`` field is always ``None`` in the mock (no real attention map
exists without a real model).

Replace with ``GlobalFeatureService`` once the ResNet50 + Linear head
checkpoint is available:
    class GlobalFeatureService:
        async def extract(self, image_bytes: bytes) -> GlobalFeatureOutput: ...
No changes to ``pipeline_runner`` or ``analysis_orchestrator`` are needed
when swapping — see the Multi-Style Mixture Analysis plan.
"""
import asyncio
import hashlib
import random
from typing import List

from chatbot.utils.cv_attributes import extract_attributes
from chatbot.utils.schemas import STYLE_CLASSES, GlobalFeatureOutput


class MockGlobalFeatureService:
    """Fake global feature extractor that returns deterministic output.

    Same image bytes always produce the same ``style_prior`` and
    ``AttributeVector``, ensuring reproducible mixture-mode pipeline runs
    without a trained ResNet50 style head.
    """

    async def extract(self, image_bytes: bytes) -> GlobalFeatureOutput:
        """Return a deterministic GlobalFeatureOutput for the given image.

        Runs the synchronous body inside ``asyncio.to_thread`` so that the
        ~150–250 ms of OpenCV work does not block the event loop when this
        method is awaited from ``AnalysisOrchestrator.analyze`` in parallel
        with the YOLO services.
        """
        return await asyncio.to_thread(self._extract_sync, image_bytes)

    @staticmethod
    def _extract_sync(image_bytes: bytes) -> GlobalFeatureOutput:
        """Synchronous body of ``extract`` — safe to off-thread.

        - ``style_prior``: RNG seeded with MD5(image_bytes), 10 raw scores
          drawn uniform in [0.05, 1.0] and normalised to sum to 1.0.
        - ``attributes``: real values from ``extract_attributes`` so the
          7-dim AttributeVector is meaningful for prompt + affinity testing
          even without a trained backbone.
        - ``gradcam_b64``: ``None`` (no real CNN attention to visualise).
        """
        seed = hashlib.md5(image_bytes).hexdigest()
        rng = random.Random(seed)
        raw_scores: List[float] = [rng.uniform(0.05, 1.0) for _ in STYLE_CLASSES]
        total = sum(raw_scores)
        style_prior = {
            style: round(score / total, 4)
            for style, score in zip(STYLE_CLASSES, raw_scores)
        }
        attributes = extract_attributes(image_bytes)
        return GlobalFeatureOutput(
            style_prior=style_prior,
            attributes=attributes,
            gradcam_b64=None,
        )

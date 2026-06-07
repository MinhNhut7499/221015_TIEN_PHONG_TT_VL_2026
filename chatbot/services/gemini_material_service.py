"""GeminiMaterialClassifierService: classify building material by reusing Gemini.

Production alternative to MockMaterialClassifierService that does NOT need a
trained YOLOv8s-cls model. It reuses the pipeline's existing GeminiService to
ask a vision-language question about the building's facade material (the same
approach as the BMAT model, but using the Gemini instance already configured
for the pipeline — so no extra dependency and nothing to fit in VRAM).

Output is the standard MaterialDistribution contract:
- ``distribution`` / ``dominant`` / ``confidence`` over the 5 controlled
  MaterialType classes (feeds the deterministic consistency rule unchanged).
- ``observed_materials``: free-text materials Gemini actually saw (possibly
  outside the 5 classes), used only as context for the downstream LLM agents.

Selected via ``settings.MATERIAL_CLASSIFIER == "gemini"``; otherwise the mock
is used. Drop-in: same ``async classify(bytes) -> MaterialDistribution``
interface, so no pipeline_runner / analysis_orchestrator logic changes.
"""
import json
import logging
from typing import Any, Dict, List

from chatbot.services.gemini_service import GeminiService
from chatbot.services.openai_service import OpenAIService
from chatbot.utils.image_utils import encode_image_base64
from chatbot.utils.prompt_builder import build_material_prompt
from chatbot.utils.schemas import MATERIAL_CLASSES, MaterialDistribution

logger = logging.getLogger(__name__)


class GeminiMaterialClassifierService:
    """Classify the dominant building material via the shared GeminiService."""

    def __init__(self, vision_llm: GeminiService) -> None:
        """Store the injected Gemini service (reused from the orchestrator).

        Args:
            vision_llm: The pipeline's configured GeminiService instance.
        """
        self._vision_llm = vision_llm

    async def classify(self, image_bytes: bytes) -> MaterialDistribution:
        """Classify the dominant material from the full building image.

        Sends the image plus a VQA-style prompt to Gemini and parses the JSON
        reply. Any LLM/parse failure degrades gracefully to a uniform
        distribution (with a logged warning) rather than breaking the pipeline.

        Args:
            image_bytes: Raw JPEG/PNG bytes of the full building image.

        Returns:
            MaterialDistribution over the 5 controlled MaterialType classes,
            plus any free-text ``observed_materials``.
        """
        try:
            image_base64 = encode_image_base64(image_bytes)
            raw = await self._vision_llm.generate_with_image(
                prompt=build_material_prompt(),
                image_base64=image_base64,
                temperature=0.0,
            )
            parsed = json.loads(OpenAIService.extract_json(raw))
            return _build_material_distribution_safe(parsed)
        except Exception as exc:  # boundary: external LLM call + JSON parse
            logger.warning(
                "Gemini material classification failed (%s); using uniform fallback.",
                exc,
            )
            return _uniform_fallback()


def _build_material_distribution_safe(parsed: Dict[str, Any]) -> MaterialDistribution:
    """Build a valid MaterialDistribution from a parsed Gemini JSON object.

    Filters the distribution to the 5 controlled classes, clips negatives,
    normalises to sum 1.0, and coerces ``observed_materials`` to a list of
    strings. Falls back to uniform if the distribution carries no usable mass.

    Args:
        parsed: Decoded JSON dict from Gemini (``distribution`` + ``observed_materials``).

    Returns:
        A normalised MaterialDistribution.
    """
    raw_dist = parsed.get("distribution", {})
    clean: Dict[str, float] = {}
    for material in MATERIAL_CLASSES:
        value = raw_dist.get(material, 0.0) if isinstance(raw_dist, dict) else 0.0
        try:
            score = float(value)
        except (TypeError, ValueError):
            score = 0.0
        clean[material] = max(score, 0.0)

    total = sum(clean.values())
    if total <= 0.0:
        return _uniform_fallback(_coerce_observed(parsed.get("observed_materials")))

    distribution = {m: round(s / total, 4) for m, s in clean.items()}
    dominant = max(distribution, key=lambda k: distribution[k])
    return MaterialDistribution(
        distribution=distribution,
        dominant=dominant,
        confidence=distribution[dominant],
        observed_materials=_coerce_observed(parsed.get("observed_materials")),
    )


def _coerce_observed(value: Any) -> List[str]:
    """Coerce a raw ``observed_materials`` value into a list of non-empty strings."""
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _uniform_fallback(observed_materials: List[str] | None = None) -> MaterialDistribution:
    """Return a uniform distribution over the 5 controlled classes."""
    share = round(1.0 / len(MATERIAL_CLASSES), 4)
    distribution = {material: share for material in MATERIAL_CLASSES}
    dominant = MATERIAL_CLASSES[0]
    return MaterialDistribution(
        distribution=distribution,
        dominant=dominant,
        confidence=distribution[dominant],
        observed_materials=observed_materials or [],
    )

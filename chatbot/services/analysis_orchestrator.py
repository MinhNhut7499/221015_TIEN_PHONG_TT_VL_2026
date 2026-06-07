"""Analysis orchestrator: entry point for the full pipeline from raw image bytes.

Responsibilities:
1. Run YOLOv8s-detection + YOLOv8s-cls + global feature extractor in parallel
   → components + material + (style_prior, attributes, gradcam)
2. Sample components (top-K per type, overall cap)
3. Delegate to PipelineRunner.run(PipelineInput) → FinalAnalysisResult

When the real models are ready:
    Replace MockYOLOService → RealYOLOService,
    MockMaterialClassifierService → MaterialClassifierService,
    MockGlobalFeatureService → GlobalFeatureService.
No other changes needed — see the Multi-Style Mixture Analysis plan.
"""
import asyncio
import logging
from collections import defaultdict
from typing import Dict, List

from app.config import settings
from chatbot.services.deepseek_service import DeepSeekService
from chatbot.services.gemini_service import GeminiService
from chatbot.services.mock_global_feature_service import MockGlobalFeatureService
from chatbot.services.mock_material_classifier import MockMaterialClassifierService
from chatbot.services.mock_yolo_service import MockYOLOService
from chatbot.services.openai_service import OpenAIService
from chatbot.services.pipeline_runner import PipelineRunner
from chatbot.utils.image_utils import encode_image_base64
from chatbot.utils.schemas import DetectedComponent, FinalAnalysisResult, PipelineInput

logger = logging.getLogger(__name__)


def is_pipeline_configured() -> bool:
    """Return True if all three LLM API keys are set in settings."""
    return bool(
        settings.GEMINI_API_KEY
        and settings.DEEPSEEK_API_KEY
        and settings.OPENAI_API_KEY
    )


class AnalysisOrchestrator:
    """Wire YOLO detection + component sampling + pipeline execution.

    Instantiated once at application startup as a lazy singleton.
    Raises RuntimeError if called without the required API keys.
    """

    def __init__(self) -> None:
        """Initialise the LLM services + image services.

        Each image service uses its trained model when the corresponding
        path is set in settings, otherwise falls back to the Mock service
        (so tests and key-less development still run). The material
        classifier has no trained model yet → always Mock.
        """
        if settings.YOLO_DETECTION_MODEL_PATH:
            from chatbot.services.yolo_service import RealYOLOService

            self._yolo = RealYOLOService(settings.YOLO_DETECTION_MODEL_PATH)
        else:
            self._yolo = MockYOLOService()

        if settings.STYLE_HEAD_MODEL_PATH:
            from chatbot.services.global_feature_service import RealGlobalFeatureService

            self._global = RealGlobalFeatureService(settings.STYLE_HEAD_MODEL_PATH)
        else:
            self._global = MockGlobalFeatureService()

        vision_llm = GeminiService(
            api_key=settings.GEMINI_API_KEY,
            model=settings.GEMINI_MODEL,
        )
        if settings.MATERIAL_CLASSIFIER == "gemini":
            from chatbot.services.gemini_material_service import (
                GeminiMaterialClassifierService,
            )

            self._material = GeminiMaterialClassifierService(vision_llm)
        else:
            self._material = MockMaterialClassifierService()
        text_llm = DeepSeekService(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
            model=settings.DEEPSEEK_MODEL,
        )
        final_llm = OpenAIService(
            api_key=settings.OPENAI_API_KEY,
            model=settings.OPENAI_MODEL,
        )
        fuser = None
        if settings.FUSER_MODEL_PATH:
            from chatbot.services.fuser_service import FuserService

            fuser = FuserService(settings.FUSER_MODEL_PATH)
        self._runner = PipelineRunner(vision_llm, text_llm, final_llm, fuser)

    async def analyze(self, image_bytes: bytes) -> FinalAnalysisResult:
        """Run the full pipeline on raw image bytes.

        Runs YOLO detection (sync, off-thread), material classification
        (async) and the global feature extractor (async, internally off-
        thread) in parallel via ``asyncio.gather``. The three results are
        bundled into ``PipelineInput`` and passed to ``PipelineRunner``.

        Args:
            image_bytes: Raw bytes of the uploaded image.

        Returns:
            FinalAnalysisResult with style, confidence, explanation, evidence.
        """
        raw_components, material, global_features = await asyncio.gather(
            asyncio.to_thread(self._yolo.detect, image_bytes),
            self._material.classify(image_bytes),
            self._global.extract(image_bytes),
        )
        sampled = _sample_components(
            raw_components,
            max_per_type=settings.PIPELINE_MAX_PER_TYPE,
            max_total=settings.PIPELINE_MAX_COMPONENTS,
        )
        top_prior_style = max(
            global_features.style_prior, key=global_features.style_prior.get
        )
        logger.info(
            "Pipeline starting: %d raw components → %d sampled; material=%s (%.2f); "
            "style_prior top=%s (%.2f)",
            len(raw_components),
            len(sampled),
            material.dominant,
            material.confidence,
            top_prior_style,
            global_features.style_prior[top_prior_style],
        )
        # Mock material is deterministic noise — flag it so the pipeline omits
        # the material evidence stream. A real classifier (gemini) is reliable.
        material_available = settings.MATERIAL_CLASSIFIER != "mock"
        pipeline_input = PipelineInput(
            components=sampled,
            material=material,
            global_features=global_features,
            material_available=material_available,
            full_image_base64=encode_image_base64(image_bytes),
        )
        return await self._runner.run(pipeline_input)


def _sample_components(
    components: List[DetectedComponent],
    max_per_type: int,
    max_total: int,
) -> List[DetectedComponent]:
    """Select top-K components per type, then cap the total.

    Picks the highest-confidence detections per component type, then
    applies a hard cap on total components entering the pipeline.

    Args:
        components: All components returned by YOLO.
        max_per_type: Maximum detections to keep per component type.
        max_total: Hard cap on total components passed to the pipeline.

    Returns:
        Filtered and capped list of DetectedComponent, ordered by confidence.
    """
    grouped: Dict[str, List[DetectedComponent]] = defaultdict(list)
    for c in components:
        grouped[c.component_type].append(c)

    selected: List[DetectedComponent] = []
    for group in grouped.values():
        top_k = sorted(group, key=lambda c: c.detection_confidence, reverse=True)
        selected.extend(top_k[:max_per_type])

    selected.sort(key=lambda c: c.detection_confidence, reverse=True)
    return selected[:max_total]


# Lazy singleton — created only when the first request arrives.
# Avoids ImportError at startup if API keys are missing.
_orchestrator: AnalysisOrchestrator | None = None


def get_orchestrator() -> AnalysisOrchestrator:
    """Return the singleton AnalysisOrchestrator, creating it on first call.

    Raises:
        RuntimeError: If called before the LLM API keys are configured.
    """
    global _orchestrator
    if _orchestrator is None:
        if not is_pipeline_configured():
            raise RuntimeError(
                "LLM pipeline is not configured. "
                "Set GEMINI_API_KEY, DEEPSEEK_API_KEY, and OPENAI_API_KEY in .env"
            )
        _orchestrator = AnalysisOrchestrator()
    return _orchestrator

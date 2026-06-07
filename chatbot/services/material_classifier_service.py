"""MaterialClassifierService: YOLOv8s-cls wrapper for production material classification.

This is the production counterpart to MockMaterialClassifierService.
When MATERIAL_MODEL_PATH is configured, the pipeline uses this service to
classify the dominant building material from the full image.

NOTE: The actual YOLOv8s-cls model is not yet trained. Calls to classify()
will raise NotImplementedError until the model file is provided. Use
MockMaterialClassifierService during development.
"""
from chatbot.utils.schemas import MaterialDistribution


class MaterialClassifierService:
    """YOLOv8s-cls wrapper that classifies the dominant material of a building.

    Args:
        model_path: Path to the trained YOLOv8s-cls .pt model file.
    """

    def __init__(self, model_path: str) -> None:
        """Store the model path. Lazy-load the model on first classify() call."""
        self._model_path = model_path
        self._model = None  # Lazy loaded

    async def classify(self, image_bytes: bytes) -> MaterialDistribution:
        """Classify the dominant building material from the full image.

        Args:
            image_bytes: Raw JPEG/PNG bytes of the full building image.

        Returns:
            MaterialDistribution with probability over 5 MaterialType classes.

        Raises:
            NotImplementedError: The YOLOv8s-cls model is not yet trained.
        """
        raise NotImplementedError(
            "MaterialClassifierService.classify() requires a trained YOLOv8s-cls "
            "model. Use MockMaterialClassifierService for development."
        )

"""RealGlobalFeatureService: ResNet50 style-prior extractor backed by style_head.pt.

Drop-in replacement for ``MockGlobalFeatureService`` — same async
``extract(image_bytes) -> GlobalFeatureOutput`` signature. Produces the
CNN ``style_prior`` (Evidence Stream 3 for Agents 5 & 7) while the 7-dim
``attributes`` vector continues to come from the real
``chatbot.utils.cv_attributes.extract_attributes``.

Model recipe (must match the Colab training exactly):
- Backbone: ``torchvision.models.resnet50`` with ImageNet weights, frozen.
- Head: ``nn.Linear(2048, 10)`` replacing ``backbone.fc``.
- Checkpoint ``style_head.pt`` is a dict ``{"state_dict", "class_names", ...}``
  where ``state_dict`` holds only the Linear head and ``class_names`` is the
  training class order (alphabetical). The class order is read from the
  checkpoint — never hard-coded — so logit i is always labelled correctly.
- Preprocessing (eval ``val_tfm``): Resize(256) → CenterCrop(224) → ToTensor
  → Normalize(ImageNet mean/std), on an RGB image.

All inference runs on CPU (see requirements.txt) and is moved off the event
loop via ``asyncio.to_thread`` so it can run in parallel with the YOLO
services from ``AnalysisOrchestrator.analyze``.
"""
import asyncio
import io
import logging
from typing import List, Optional

import numpy as np
import torch
from PIL import Image
from torchvision import models, transforms
from torchvision.models import ResNet50_Weights

from app.config import settings
from chatbot.utils.cv_attributes import extract_attributes
from chatbot.utils.schemas import STYLE_CLASSES, GlobalFeatureOutput

logger = logging.getLogger(__name__)

_IMAGENET_MEAN = [0.485, 0.456, 0.406]
_IMAGENET_STD = [0.229, 0.224, 0.225]
_INPUT_SIZE = 224
_RESIZE_SIZE = 256


class RealGlobalFeatureService:
    """Extract a ResNet50 style prior + CV attributes for a full building image.

    Args:
        model_path: Path to the trained style head checkpoint (style_head.pt).
    """

    def __init__(self, model_path: str) -> None:
        """Store the checkpoint path; defer model construction until first use."""
        self._model_path = model_path
        self._model = None  # Lazy-loaded torch.nn.Module.
        self._resize_crop = None  # Lazy-built Resize+CenterCrop transform.
        self._normalize = None  # Lazy-built ToTensor+Normalize transform.
        self._class_names: List[str] = []

    def _ensure_model(self) -> None:
        """Build ResNet50 + Linear head and load the trained head weights once."""
        if self._model is not None:
            return
        logger.info("Loading ResNet50 style head from %s", self._model_path)
        backbone = models.resnet50(weights=ResNet50_Weights.IMAGENET1K_V2)
        backbone.fc = torch.nn.Linear(2048, len(STYLE_CLASSES))

        checkpoint = torch.load(self._model_path, map_location="cpu")
        backbone.fc.load_state_dict(checkpoint["state_dict"])
        class_names = list(checkpoint["class_names"])
        if set(class_names) != set(STYLE_CLASSES):
            raise ValueError(
                "style_head checkpoint class_names do not match STYLE_CLASSES: "
                f"{class_names} vs {STYLE_CLASSES}"
            )

        backbone.eval()
        self._model = backbone
        self._class_names = class_names
        # Resize + crop only, shared by both paths; ToTensor/Normalize for the
        # model input, raw [0,1] array for the Grad-CAM overlay.
        self._resize_crop = transforms.Compose(
            [
                transforms.Resize(_RESIZE_SIZE),
                transforms.CenterCrop(_INPUT_SIZE),
            ]
        )
        self._normalize = transforms.Compose(
            [
                transforms.ToTensor(),
                transforms.Normalize(mean=_IMAGENET_MEAN, std=_IMAGENET_STD),
            ]
        )

    async def extract(self, image_bytes: bytes) -> GlobalFeatureOutput:
        """Return the global feature bundle (style prior + CV attributes).

        The ResNet50 forward pass and the OpenCV attribute extraction both
        run inside ``asyncio.to_thread`` so the event loop stays responsive
        when this is awaited alongside the YOLO services.
        """
        return await asyncio.to_thread(self._extract_sync, image_bytes)

    def _extract_sync(self, image_bytes: bytes) -> GlobalFeatureOutput:
        """Synchronous body of ``extract`` — safe to off-thread."""
        self._ensure_model()
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        cropped = self._resize_crop(image)  # type: ignore[misc]
        tensor = self._normalize(cropped).unsqueeze(0)  # type: ignore[misc]
        with torch.inference_mode():
            logits = self._model(tensor)  # type: ignore[misc]
            # Temperature scaling: T>1 softens an over-confident prior.
            temperature = max(1e-3, settings.STYLE_HEAD_TEMPERATURE)
            probs = torch.softmax(logits / temperature, dim=1)[0]

        style_prior = {
            self._class_names[i]: float(probs[i]) for i in range(len(self._class_names))
        }
        attributes = extract_attributes(image_bytes)
        gradcam_b64 = self._maybe_gradcam(cropped, int(torch.argmax(probs)))
        return GlobalFeatureOutput(
            style_prior=style_prior,
            attributes=attributes,
            gradcam_b64=gradcam_b64,
        )

    def _maybe_gradcam(self, cropped_image: Image.Image, target_class: int) -> Optional[str]:
        """Build a Grad-CAM overlay for ``target_class`` if enabled, else None.

        Uses a fresh grad-enabled forward (separate from the no-grad style-prior
        pass). Imported lazily so the heavy pytorch-grad-cam dependency is only
        loaded when the feature is actually used.
        """
        if not settings.ENABLE_GRADCAM:
            return None
        from chatbot.utils.gradcam import generate_gradcam

        rgb = np.asarray(cropped_image, dtype=np.float32) / 255.0
        tensor = self._normalize(cropped_image).unsqueeze(0)  # type: ignore[misc]
        return generate_gradcam(self._model, tensor, rgb, target_class)

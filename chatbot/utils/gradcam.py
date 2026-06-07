"""Grad-CAM helper for the ResNet50 style head (Evidence Stream 3).

Produces a class-activation heatmap overlaid on the (preprocessed) input image
so the frontend can show *where* the CNN looked when forming its style prior.
Targets ``resnet50.layer4[-1]`` — the canonical Grad-CAM layer for ResNet.

Runs on CPU (torch is CPU-only here; see requirements.txt). A single backward
pass over ResNet50 costs a few hundred ms — acceptable for one image per
analysis. Only invoked by ``RealGlobalFeatureService`` when
``settings.ENABLE_GRADCAM`` is True.
"""
import base64
import io
import logging
from typing import Optional

import numpy as np
import torch
from PIL import Image
from pytorch_grad_cam import GradCAM
from pytorch_grad_cam.utils.image import show_cam_on_image
from pytorch_grad_cam.utils.model_targets import ClassifierOutputTarget

logger = logging.getLogger(__name__)


def generate_gradcam(
    model: torch.nn.Module,
    input_tensor: torch.Tensor,
    rgb_image: np.ndarray,
    target_class: int,
) -> Optional[str]:
    """Return a base64-encoded PNG of the Grad-CAM heatmap overlaid on the image.

    Args:
        model: The ResNet50 (backbone + Linear head) in eval mode.
        input_tensor: Normalised input, shape ``(1, 3, H, W)``.
        rgb_image: The matching un-normalised image as float32 in ``[0, 1]``,
            shape ``(H, W, 3)`` — same spatial size as ``input_tensor``.
        target_class: Index of the style logit to explain (usually the argmax).

    Returns:
        Base64 PNG string of the overlay, or None if Grad-CAM failed (logged).
    """
    try:
        target_layers = [model.layer4[-1]]  # type: ignore[index]
        with GradCAM(model=model, target_layers=target_layers) as cam:
            grayscale_cam = cam(
                input_tensor=input_tensor,
                targets=[ClassifierOutputTarget(target_class)],
            )[0]
        overlay = show_cam_on_image(rgb_image, grayscale_cam, use_rgb=True)
        buffer = io.BytesIO()
        Image.fromarray(overlay).save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("ascii")
    except Exception as exc:  # noqa: BLE001 — boundary: never break analysis on CAM failure
        logger.warning("Grad-CAM generation failed: %s", exc)
        return None

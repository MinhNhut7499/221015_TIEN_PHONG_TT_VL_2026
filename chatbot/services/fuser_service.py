"""Learned, calibrated fuser that turns the numeric evidence streams into a
final style distribution — the production replacement for LLM-as-judge fusion.

The 31-dim feature vector is built by ONE function (``build_fuser_features``)
used BOTH offline (scripts/build_fuser_dataset.py) and online (the pipeline),
so there is no train/serve skew. Layout (fixed order):

    [ 0:10]  resnet  — log P(style|image) from the ResNet50 head
    [10:18]  component — max YOLO detection confidence per ComponentType
    [18:25]  attribute — 7 classical-CV attributes
    [25:30]  material — 5-class probability (zeros when unavailable)
    [30]     flag     — 1.0 if material is real, else 0.0

The model file (``models/fuser.joblib``) is a fitted sklearn Pipeline
(scaler + classifier, optionally calibrated). It is trained ONCE offline and
frozen — inference only loads + predicts, it does NOT learn per request. When
no model file is present the caller falls back to ``numeric_fuse``.
"""
import logging
import math
from typing import Dict, List, Optional

import numpy as np

from chatbot.utils.schemas import (
    COMPONENT_TYPES,
    MATERIAL_CLASSES,
    STYLE_CLASSES,
    AttributeVector,
    DetectedComponent,
    MaterialDistribution,
)

logger = logging.getLogger(__name__)

_EPS = 1e-6

# Column slices (for the ColumnTransformer in scripts/train_fuser.py).
RESNET_SLICE = slice(0, 10)
COMPONENT_SLICE = slice(10, 18)
ATTRIBUTE_SLICE = slice(18, 25)
MATERIAL_SLICE = slice(25, 30)
FLAG_INDEX = 30
FEATURE_DIM = 31
# Columns that need StandardScaler (continuous, non-bounded); the rest are
# already in [0, 1] / a probability simplex and pass through unscaled.
SCALE_COLUMNS: List[int] = list(range(0, 10)) + list(range(18, 25))


def build_fuser_features(
    style_prior: Dict[str, float],
    attributes: AttributeVector,
    components: List[DetectedComponent],
    material: Optional[MaterialDistribution],
    material_available: bool,
) -> np.ndarray:
    """Assemble the fixed-order 31-dim feature vector (raw; scaling done by model).

    Missing sources collapse to zeros (no components → 8 zeros; material
    unavailable → 5 zeros + flag 0) so the model learns to ignore them.
    """
    resnet = [math.log(max(style_prior.get(s, 0.0), _EPS)) for s in STYLE_CLASSES]

    comp_max: Dict[str, float] = {t: 0.0 for t in COMPONENT_TYPES}
    for c in components:
        if c.component_type in comp_max:
            comp_max[c.component_type] = max(
                comp_max[c.component_type], c.detection_confidence
            )
    comp = [comp_max[t] for t in COMPONENT_TYPES]

    attr = [
        attributes.symmetry_score,
        attributes.vertical_dominance,
        attributes.horizontal_dominance,
        attributes.curvature_score,
        attributes.surface_roughness,
        attributes.edge_density,
        attributes.edge_orientation_entropy,
    ]

    if material_available and material is not None:
        mat = [float(material.distribution.get(m, 0.0)) for m in MATERIAL_CLASSES]
        flag = 1.0
    else:
        mat = [0.0] * len(MATERIAL_CLASSES)
        flag = 0.0

    return np.array(resnet + comp + attr + mat + [flag], dtype=np.float64)


class FuserService:
    """Load a trained fuser and predict a calibrated style distribution."""

    def __init__(self, model_path: str) -> None:
        """Store the path; lazy-load the joblib model on first predict."""
        self._model_path = model_path
        self._model = None  # Lazy-loaded sklearn Pipeline.

    def _ensure_model(self) -> None:
        if self._model is None:
            import joblib

            logger.info("Loading learned fuser from %s", self._model_path)
            self._model = joblib.load(self._model_path)

    def predict(
        self,
        style_prior: Dict[str, float],
        attributes: AttributeVector,
        components: List[DetectedComponent],
        material: Optional[MaterialDistribution],
        material_available: bool,
    ) -> Dict[str, float]:
        """Return ``{style: probability}`` over STYLE_CLASSES from the learned fuser."""
        self._ensure_model()
        x = build_fuser_features(
            style_prior, attributes, components, material, material_available
        ).reshape(1, -1)
        proba = self._model.predict_proba(x)[0]  # type: ignore[union-attr]
        classes = self._model.classes_  # type: ignore[union-attr]
        dist = {STYLE_CLASSES[int(c)]: float(p) for c, p in zip(classes, proba)}
        total = sum(dist.values()) or 1.0
        return {s: dist.get(s, 0.0) / total for s in STYLE_CLASSES}

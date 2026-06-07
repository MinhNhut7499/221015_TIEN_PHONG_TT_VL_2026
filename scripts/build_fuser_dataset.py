"""Build the fuser training table: each labelled image → 31-dim feature + label.

Runs the real ResNet + YOLO extractors over every image in the dataset (NO LLM,
NO material service — material is treated as unavailable, matching the mock
default). Saves features + label + building group + original split to
``models/fuser_dataset.npz`` for scripts/train_fuser.py.

Run from repo root (model paths from .env):
    python scripts/build_fuser_dataset.py
"""
import asyncio
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from chatbot.services.fuser_service import build_fuser_features  # noqa: E402
from chatbot.services.global_feature_service import RealGlobalFeatureService  # noqa: E402
from chatbot.services.yolo_service import RealYOLOService  # noqa: E402
from chatbot.utils.schemas import STYLE_CLASSES  # noqa: E402
from scripts.dataset_utils import group_key, iter_split_images  # noqa: E402

_SPLITS = ("train", "val", "test")
_OUT = Path("models/fuser_dataset.npz")


def main() -> None:
    root = Path("data/style_dataset")
    yolo = RealYOLOService(settings.YOLO_DETECTION_MODEL_PATH)
    glob = RealGlobalFeatureService(settings.STYLE_HEAD_MODEL_PATH)

    X, y, groups, splits = [], [], [], []
    t0 = time.monotonic()
    for split in _SPLITS:
        sdir = root / split
        if not sdir.is_dir():
            continue
        n = 0
        for img, label in iter_split_images(sdir):
            if label not in STYLE_CLASSES:
                continue
            data = img.read_bytes()
            gf = asyncio.run(glob.extract(data))
            comps = yolo.detect(data)
            feat = build_fuser_features(
                gf.style_prior, gf.attributes, comps, None, material_available=False
            )
            X.append(feat)
            y.append(STYLE_CLASSES.index(label))
            groups.append(group_key(img))
            splits.append(split)
            n += 1
            if n % 50 == 0:
                print(f"  {split}: {n} done ({time.monotonic()-t0:.0f}s)")
        print(f"{split}: {n} images")

    _OUT.parent.mkdir(exist_ok=True)
    np.savez(
        _OUT,
        X=np.array(X, dtype=np.float64),
        y=np.array(y, dtype=np.int64),
        groups=np.array(groups, dtype=object),
        split=np.array(splits, dtype=object),
    )
    print(f"\nSaved {len(X)} feature rows → {_OUT} ({time.monotonic()-t0:.0f}s)")


if __name__ == "__main__":
    main()

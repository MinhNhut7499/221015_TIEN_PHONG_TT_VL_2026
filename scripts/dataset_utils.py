"""Shared dataset helpers for the fuser scripts (group key + image iteration)."""
import re
from pathlib import Path
from typing import Iterator, Tuple

_IMG_EXTS = ("*.jpg", "*.jpeg", "*.png")
_TRAILING_INDEX = re.compile(r"_\d+$")


def group_key(image_path: Path) -> str:
    """Return a building/query group id for an image (for leakage-free splits).

    Scraped filenames repeat the same building under one query, e.g.
    ``ddg_notre_dame_gothic_architecture_22.jpg`` and ``..._25.jpg`` are the
    SAME building. We strip the trailing ``_<index>`` and prefix the style
    folder so the same query never crosses styles. Numeric-only stems
    (``000001``) have no index suffix → each is its own group.
    """
    stem = image_path.stem
    stripped = _TRAILING_INDEX.sub("", stem) or stem
    return f"{image_path.parent.name}::{stripped}"


def iter_split_images(split_dir: Path) -> Iterator[Tuple[Path, str]]:
    """Yield (image_path, style_label) for every image under a split directory.

    The style label is the immediate class sub-folder name (the dataset's
    local "Art Noveau" typo is normalised to "Art Nouveau").
    """
    for class_dir in sorted(p for p in split_dir.iterdir() if p.is_dir()):
        label = class_dir.name.replace("Art Noveau", "Art Nouveau")
        paths = []
        for ext in _IMG_EXTS:
            paths.extend(class_dir.glob(ext))
        for img in sorted(paths):
            yield img, label

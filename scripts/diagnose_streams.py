"""Per-stream diagnosis + attribute ablation for the style pipeline.

Answers "which stream is wrong?" without any LLM calls. For one image it prints
each stream's independent verdict; for a labelled folder it reports per-stream
top-1 accuracy and whether the attribute tie-breaker HELPS or HURTS.

Usage (from repo root, with model paths set in .env):
    python scripts/diagnose_streams.py data/style_dataset/test/Art Nouveau/000019.jpg
    python scripts/diagnose_streams.py data/style_dataset/test --limit 8
"""
import argparse
import sys
from collections import defaultdict
from pathlib import Path

# Allow running as a script from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from chatbot.services.global_feature_service import RealGlobalFeatureService  # noqa: E402
from chatbot.services.yolo_service import RealYOLOService  # noqa: E402
from chatbot.utils.fusion import numeric_fuse  # noqa: E402
from chatbot.utils.rule_checker import compute_attribute_affinity  # noqa: E402

_FOLDER_FIX = {"Art Noveau": "Art Nouveau"}  # local dataset typo


def _top1(scores):
    return max(scores, key=scores.get) if scores else None


def _streams_for_image(image_bytes, yolo, glob):
    """Return (resnet_top1, attr_top1, fused_top1, fused_noattr_top1, components)."""
    gf = glob.extract_sync(image_bytes) if hasattr(glob, "extract_sync") else None
    if gf is None:
        import asyncio

        gf = asyncio.run(glob.extract(image_bytes))
    affinity = compute_attribute_affinity(gf.attributes)
    comps = yolo.detect(image_bytes)
    fused = numeric_fuse(
        None, gf.style_prior, affinity,
        weight_votes=settings.FUSION_WEIGHT_VOTES,
        weight_prior=settings.FUSION_WEIGHT_PRIOR,
        weight_attribute=settings.FUSION_WEIGHT_ATTRIBUTE,
    )
    fused_noattr = numeric_fuse(
        None, gf.style_prior, None,
        weight_votes=settings.FUSION_WEIGHT_VOTES,
        weight_prior=settings.FUSION_WEIGHT_PRIOR,
        weight_attribute=settings.FUSION_WEIGHT_ATTRIBUTE,
    )
    return (
        gf.style_prior, affinity, fused, fused_noattr,
        [(c.component_type, round(c.detection_confidence, 2)) for c in comps],
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", help="image file or labelled folder (split dir)")
    ap.add_argument("--limit", type=int, default=8, help="images per class in folder mode")
    args = ap.parse_args()

    yolo = RealYOLOService(settings.YOLO_DETECTION_MODEL_PATH)
    glob = RealGlobalFeatureService(settings.STYLE_HEAD_MODEL_PATH)
    target = Path(args.path)

    if target.is_file():
        sp, aff, fused, fused_na, comps = _streams_for_image(
            target.read_bytes(), yolo, glob
        )
        print(f"\n{target.name}")
        print(f"  ResNet top-1     : {_top1(sp)}   {sorted(sp.items(), key=lambda x:-x[1])[:3]}")
        print(f"  Attribute top-1  : {_top1(aff)}  {sorted(aff.items(), key=lambda x:-x[1])[:3]}")
        print(f"  Fused (w/ attr)  : {_top1(fused)}")
        print(f"  Fused (no attr)  : {_top1(fused_na)}")
        print(f"  YOLO components  : {comps}")
        return

    # Folder mode: per-stream accuracy + ablation
    hit = defaultdict(int)
    total = 0
    for class_dir in sorted(p for p in target.iterdir() if p.is_dir()):
        true_label = _FOLDER_FIX.get(class_dir.name, class_dir.name)
        imgs = sorted(class_dir.glob("*.jp*g")) + sorted(class_dir.glob("*.png"))
        for img in imgs[: args.limit]:
            sp, aff, fused, fused_na, _ = _streams_for_image(img.read_bytes(), yolo, glob)
            total += 1
            hit["resnet"] += _top1(sp) == true_label
            hit["attribute"] += _top1(aff) == true_label
            hit["fused_with_attr"] += _top1(fused) == true_label
            hit["fused_no_attr"] += _top1(fused_na) == true_label

    print(f"\nPer-stream top-1 accuracy over {total} images:")
    for k in ["resnet", "attribute", "fused_with_attr", "fused_no_attr"]:
        print(f"  {k:16s} {hit[k]/max(1,total):.3f}")
    verdict = (
        "ATTRIBUTE HELPS" if hit["fused_with_attr"] > hit["fused_no_attr"]
        else "ATTRIBUTE HURTS/NEUTRAL — keep it tie-breaker-only or drop"
    )
    print(f"\nAblation: {verdict}")


if __name__ == "__main__":
    main()

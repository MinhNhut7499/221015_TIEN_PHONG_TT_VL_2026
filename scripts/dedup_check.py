"""Data hygiene: near-duplicate + building-level leakage report (L1 + L2).

Run from repo root:
    python scripts/dedup_check.py                # default data/style_dataset

Reports:
- cross-split near-duplicate image pairs (pHash Hamming ≤ threshold) — these
  inflate metrics (the "same" image in train and test).
- building-level group leakage: a group_key appearing in >1 split.

It does NOT delete anything (read-only audit); it prints what a clean split
would need to remove so the fuser metrics are trustworthy.
"""
import argparse
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import imagehash
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.dataset_utils import group_key, iter_split_images  # noqa: E402

_SPLITS = ("train", "val", "test")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="data/style_dataset")
    ap.add_argument("--hamming", type=int, default=6, help="max pHash distance for near-dup")
    args = ap.parse_args()
    root = Path(args.root)

    # Collect images + hashes per split.
    split_of: dict = {}
    group_of: dict = {}
    hashes: list = []
    groups_per_split: dict = defaultdict(set)
    for split in _SPLITS:
        sdir = root / split
        if not sdir.is_dir():
            continue
        for img, _label in iter_split_images(sdir):
            try:
                h = imagehash.phash(Image.open(img).convert("RGB"))
            except Exception as exc:  # boundary: corrupt image file
                print(f"  ! skip unreadable {img}: {exc}")
                continue
            split_of[img] = split
            group_of[img] = group_key(img)
            groups_per_split[split].add(group_key(img))
            hashes.append((img, h))

    print(f"Indexed {len(hashes)} images across splits.")

    # L1 — cross-split near-duplicates (O(n^2); fine for a few-thousand set).
    cross_pairs = []
    for (ia, ha), (ib, hb) in combinations(hashes, 2):
        if split_of[ia] == split_of[ib]:
            continue
        if (ha - hb) <= args.hamming:
            cross_pairs.append((ia, ib))
    print(f"\nL1 cross-split near-duplicate pairs (Hamming ≤ {args.hamming}): {len(cross_pairs)}")
    for ia, ib in cross_pairs[:20]:
        print(f"  {split_of[ia]}:{ia.name}  ~  {split_of[ib]}:{ib.name}")
    if len(cross_pairs) > 20:
        print(f"  ... +{len(cross_pairs) - 20} more")

    # L2 — building-level group leakage across splits.
    leaks = []
    for sa, sb in combinations(_SPLITS, 2):
        shared = groups_per_split.get(sa, set()) & groups_per_split.get(sb, set())
        for g in sorted(shared):
            leaks.append((sa, sb, g))
    print(f"\nL2 building groups appearing in >1 split: {len(leaks)}")
    for sa, sb, g in leaks[:20]:
        print(f"  {sa} ∩ {sb}: {g}")
    if len(leaks) > 20:
        print(f"  ... +{len(leaks) - 20} more")

    verdict = "CLEAN" if not cross_pairs and not leaks else "LEAKAGE FOUND → re-split by group (scripts/train_fuser.py does this)"
    print(f"\nVerdict: {verdict}")


if __name__ == "__main__":
    main()

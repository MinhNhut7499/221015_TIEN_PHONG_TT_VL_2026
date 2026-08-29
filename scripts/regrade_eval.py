"""Re-score an existing evaluate_openvocab.py CSV under tolerant grading rules.

ZERO LLM calls — this only re-reads the per-image rows already produced by a run
and recomputes top-1 at three strictness levels, to separate genuine errors from
GRADING ARTIFACTS:

    strict           — the harness's exact KB-id top-1 (``top1_hit`` column).
    revival-tolerant — strict OR the prediction is an era/Revival twin of the
                       ground truth (``Byzantine`` vs ``Byzantine Revival``,
                       ``Renaissance`` vs ``Renaissance Revival``...). These look
                       visually identical and differ only by PERIOD, which an
                       AI-generated image cannot encode — so penalising them is a
                       grading-strictness artifact, not a model error.
    family-tolerant  — strict OR same KB family/parent (``family_hit`` column),
                       i.e. right family, possibly wrong child style.

Prints overall + per diagnostic group (broken / hard / guard) and lists exactly
which broken images each tolerance level rescues, so the numbers can be checked
by eye.

Usage (from project root):
    python scripts/regrade_eval.py results/eval_C_baseline.csv
"""
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path
from typing import Dict, List

# Tokens stripped when testing whether two style names are era/Revival twins.
_DROP_TOKENS = {"revival", "neo", "style", "architecture", "the"}


def _norm(name: str) -> str:
    """Normalise a style name for era/Revival-twin matching.

    Lowercases, splits on non-alphanumerics, drops era/Revival marker tokens, and
    rejoins. So ``"Byzantine Revival"`` and ``"Byzantine"`` → ``"byzantine"``;
    ``"Neo-Gothic"`` and ``"Gothic"`` → ``"gothic"``.
    """
    tokens = [t for t in re.split(r"[^a-z0-9]+", name.lower()) if t]
    kept = [t for t in tokens if t not in _DROP_TOKENS]
    return " ".join(kept) if kept else " ".join(tokens)


def _revival_twin(gt: str, pred: str) -> bool:
    """True if gt and pred are the same style modulo an era/Revival marker."""
    g, p = _norm(gt), _norm(pred)
    return bool(g) and g == p


def _load(path: Path) -> List[dict]:
    """Read the eval CSV rows (each a dict keyed by the CSV header)."""
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _int(row: dict, key: str) -> int:
    """Read a 0/1 column as int (0 when missing/blank)."""
    return int(row.get(key, "0") or 0)


def _hits(rows: List[dict]) -> Dict[str, int]:
    """Count strict / revival-tolerant / family-tolerant top-1 hits over rows."""
    strict = sum(_int(r, "top1_hit") for r in rows)
    revival = sum(
        1 for r in rows
        if _int(r, "top1_hit") or _revival_twin(r["gt_style"], r["pred_style"])
    )
    family = sum(
        1 for r in rows
        if _int(r, "top1_hit") or _int(r, "family_hit")
    )
    return {"strict": strict, "revival": revival, "family": family}


def _pct(n: int, d: int) -> str:
    """Format n/d as 'n/d (xx.x%)'."""
    return f"{n}/{d} ({100.0 * n / d:.1f}%)" if d else "0/0 (n/a)"


def _print_block(title: str, rows: List[dict]) -> None:
    """Print the three tolerance levels for one set of rows."""
    if not rows:
        return
    h = _hits(rows)
    n = len(rows)
    print(f"  {title:8} (n={n:3}) "
          f"strict={_pct(h['strict'], n):>15}  "
          f"revival={_pct(h['revival'], n):>15}  "
          f"family={_pct(h['family'], n):>15}")


def main() -> int:
    """Re-grade an eval CSV and print strict vs tolerant top-1, with rescues."""
    parser = argparse.ArgumentParser(description="Tolerant re-grading of an eval CSV")
    parser.add_argument("csv_path", help="evaluate_openvocab.py output CSV")
    args = parser.parse_args()

    path = Path(args.csv_path)
    if not path.is_file():
        print(f"ERROR: CSV not found: {path}")
        return 1
    rows = [r for r in _load(path) if (r.get("error") or "") == "" and int(r.get("n_candidates", "0") or 0) > 0]
    if not rows:
        print("ERROR: no scored rows.")
        return 1

    print(f"Re-grading {len(rows)} scored images from {path}\n")
    _print_block("ALL", rows)
    for grp in ("broken", "hard", "guard"):
        _print_block(grp, [r for r in rows if r.get("group") == grp])

    # Which broken images get rescued purely by era/Revival tolerance?
    rescued = [
        r for r in rows
        if r.get("group") == "broken"
        and not _int(r, "top1_hit")
        and _revival_twin(r["gt_style"], r["pred_style"])
    ]
    print(f"\nBROKEN images rescued by era/Revival tolerance ({len(rescued)}):")
    for r in sorted(rescued, key=lambda x: x["prompt_id"]):
        print(f"  id={r['prompt_id']:>3} {r['generator']:7} "
              f"{r['gt_style'][:26]:26} -> {r['pred_style'][:26]}")

    # Family-only rescues (right family, not an exact era twin) — for context.
    fam_only = [
        r for r in rows
        if r.get("group") == "broken"
        and not _int(r, "top1_hit")
        and not _revival_twin(r["gt_style"], r["pred_style"])
        and _int(r, "family_hit")
    ]
    print(f"\nBROKEN images right-family-only (not era twins) ({len(fam_only)}):")
    for r in sorted(fam_only, key=lambda x: x["prompt_id"]):
        print(f"  id={r['prompt_id']:>3} {r['generator']:7} "
              f"{r['gt_style'][:26]:26} -> {r['pred_style'][:26]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

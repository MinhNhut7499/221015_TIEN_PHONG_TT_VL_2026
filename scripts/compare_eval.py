"""Compare two evaluate_openvocab.py result CSVs (e.g. arbiter vs consensus).

Joins the per-image rows by (prompt_id, generator) and reports, overall and per
diagnostic group, how top-1 accuracy moved — plus the exact images that FLIPPED
(gained or lost top-1). The decision rule for the W1 redesign:

    accept the new mode iff  broken top-1 UP  AND  guard top-1 NOT down.

Usage (from project root):
    python scripts/compare_eval.py results/eval_C_baseline.csv results/eval_C_consensus.csv
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict, List, Tuple

_KEY = Tuple[str, str]  # (prompt_id, generator)


def _load(path: Path) -> Dict[_KEY, dict]:
    """Read an eval CSV into {(prompt_id, generator): row}."""
    rows: Dict[_KEY, dict] = {}
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rows[(row["prompt_id"], row["generator"])] = row
    return rows


def _t1(row: dict) -> int:
    """top1_hit as int (0/1)."""
    return int(row.get("top1_hit", "0") or 0)


def _group_table(
    before: Dict[_KEY, dict], after: Dict[_KEY, dict], keys: List[_KEY]
) -> None:
    """Print overall + per-group top-1 before/after and the net delta."""
    groups = ["broken", "hard", "guard"]
    buckets: Dict[str, List[_KEY]] = {g: [] for g in groups}
    buckets["ALL"] = []
    for k in keys:
        buckets["ALL"].append(k)
        g = before[k].get("group", "") or after[k].get("group", "")
        if g in buckets:
            buckets[g].append(k)

    print(f"{'group':8} {'n':>4} {'before':>9} {'after':>9} {'delta':>7}")
    for g in ["ALL", *groups]:
        ks = buckets[g]
        if not ks:
            continue
        b = sum(_t1(before[k]) for k in ks)
        a = sum(_t1(after[k]) for k in ks)
        print(f"{g:8} {len(ks):>4} {b:>4}/{len(ks):<4} {a:>4}/{len(ks):<4} "
              f"{a - b:>+7}")


def _flips(
    before: Dict[_KEY, dict], after: Dict[_KEY, dict], keys: List[_KEY]
) -> None:
    """List images that gained (0→1) or lost (1→0) top-1, grouped by direction."""
    gained = [k for k in keys if not _t1(before[k]) and _t1(after[k])]
    lost = [k for k in keys if _t1(before[k]) and not _t1(after[k])]

    def _show(title: str, ks: List[_KEY]) -> None:
        print(f"\n{title} ({len(ks)}):")
        for k in sorted(ks, key=lambda x: (before[x].get("group", ""), x)):
            row = after[k]
            grp = row.get("group", "")
            print(f"  [{grp:6}] id={k[0]:>3} {k[1]:7} "
                  f"gt={row.get('gt_style','')[:24]:24} "
                  f"before={before[k].get('pred_style','')[:20]:20} "
                  f"after={row.get('pred_style','')[:20]:20}")

    _show("GAINED top-1 (before wrong → after right)", gained)
    _show("LOST top-1 (before right → after wrong) — regressions", lost)


def main() -> int:
    """Diff two eval CSVs and print the per-group movement + flips."""
    parser = argparse.ArgumentParser(description="Compare two eval result CSVs")
    parser.add_argument("before", help="baseline CSV (e.g. arbiter mode)")
    parser.add_argument("after", help="new CSV (e.g. consensus mode)")
    args = parser.parse_args()

    before = _load(Path(args.before))
    after = _load(Path(args.after))
    keys = [k for k in before if k in after]
    if not keys:
        print("ERROR: the two CSVs share no (prompt_id, generator) rows.")
        return 1

    print(f"Comparing {len(keys)} shared images\n  before = {args.before}"
          f"\n  after  = {args.after}\n")
    _group_table(before, after, keys)
    _flips(before, after, keys)

    guard_lost = [
        k for k in keys
        if (before[k].get("group") == "guard")
        and _t1(before[k]) and not _t1(after[k])
    ]
    broken_b = sum(_t1(before[k]) for k in keys if before[k].get("group") == "broken")
    broken_a = sum(_t1(after[k]) for k in keys if before[k].get("group") == "broken")
    print("\n--- verdict ---")
    print(f"broken top-1: {broken_b} -> {broken_a} ({broken_a - broken_b:+d})")
    print(f"guard regressions: {len(guard_lost)}")
    ok = broken_a > broken_b and not guard_lost
    print("ACCEPT new mode" if ok else "DO NOT accept yet (review trade-off)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

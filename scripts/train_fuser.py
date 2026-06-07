"""Train + calibrate the learned fuser with a leakage-free group split.

Reads models/fuser_dataset.npz (from build_fuser_dataset.py), RE-SPLITS by
building group (ignoring the leaky folder split), trains a logistic-regression
fuser, calibrates it on validation, runs a risk-coverage sweep, reports test
metrics, and saves models/fuser.joblib.

Run from repo root:
    python scripts/train_fuser.py --target-acc 0.85
"""
import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chatbot.services.fuser_service import SCALE_COLUMNS, FEATURE_DIM  # noqa: E402
from chatbot.utils.metrics import (  # noqa: E402
    expected_calibration_error,
    pick_threshold,
    risk_coverage_curve,
)
from chatbot.utils.schemas import STYLE_CLASSES  # noqa: E402

_DATA = Path("models/fuser_dataset.npz")
_OUT = Path("models/fuser.joblib")


def _group_split(groups, y, seed=42):
    """Group-disjoint train/val/test (~70/15/15) via GroupShuffleSplit."""
    from sklearn.model_selection import GroupShuffleSplit

    idx = np.arange(len(y))
    gss1 = GroupShuffleSplit(n_splits=1, test_size=0.15, random_state=seed)
    trainval_idx, test_idx = next(gss1.split(idx, y, groups))
    gss2 = GroupShuffleSplit(n_splits=1, test_size=0.1765, random_state=seed)  # ~15% overall
    tr_rel, val_rel = next(
        gss2.split(trainval_idx, y[trainval_idx], groups[trainval_idx])
    )
    return trainval_idx[tr_rel], trainval_idx[val_rel], test_idx


def _build_pipeline(C):
    from sklearn.compose import ColumnTransformer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    passthrough = [i for i in range(FEATURE_DIM) if i not in SCALE_COLUMNS]
    pre = ColumnTransformer(
        [("scale", StandardScaler(), SCALE_COLUMNS), ("pass", "passthrough", passthrough)]
    )
    # Multinomial is the default in sklearn ≥1.5; class_weight handles the
    # dataset's mild imbalance (Gothic ≫ High-tech).
    clf = LogisticRegression(class_weight="balanced", C=C, max_iter=3000)
    return Pipeline([("pre", pre), ("clf", clf)])


def _topk_acc(proba, y_true, k=3):
    topk = np.argsort(proba, axis=1)[:, -k:]
    return float(np.mean([y_true[i] in topk[i] for i in range(len(y_true))]))


def main() -> None:
    import joblib
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.metrics import balanced_accuracy_score, confusion_matrix

    ap = argparse.ArgumentParser()
    ap.add_argument("--target-acc", type=float, default=0.85)
    args = ap.parse_args()

    d = np.load(_DATA, allow_pickle=True)
    X, y, groups = d["X"], d["y"], d["groups"]
    tr, val, te = _group_split(groups, y)
    print(f"Split (group-disjoint): train={len(tr)} val={len(val)} test={len(te)}")
    assert not (set(groups[tr]) & set(groups[val]) & set(groups[te]))

    # Tune C on validation by balanced accuracy.
    best_C, best_bal, best_pipe = None, -1.0, None
    for C in [0.05, 0.1, 0.3, 1.0, 3.0]:
        pipe = _build_pipeline(C).fit(X[tr], y[tr])
        bal = balanced_accuracy_score(y[val], pipe.predict(X[val]))
        print(f"  C={C:<4} val balanced_acc={bal:.3f}")
        if bal > best_bal:
            best_C, best_bal, best_pipe = C, bal, pipe
    print(f"Best C={best_C} (val balanced_acc={best_bal:.3f})")

    # Calibrate with internal CV on TRAIN (val/test stay clean held-out), then
    # PICK the variant with the lowest VALIDATION ECE — isotonic overfits on
    # small data, so sigmoid (Platt) often wins; keep uncalibrated if best.
    candidates = {"uncalibrated": best_pipe}
    for method in ("sigmoid", "isotonic"):
        candidates[method] = CalibratedClassifierCV(
            _build_pipeline(best_C), method=method, cv=5
        ).fit(X[tr], y[tr])
    val_ece = {
        name: expected_calibration_error(m.predict_proba(X[val]), y[val])
        for name, m in candidates.items()
    }
    chosen = min(val_ece, key=val_ece.get)
    print("\nValidation ECE by calibration: "
          + ", ".join(f"{k}={v:.3f}" for k, v in val_ece.items())
          + f"  → chosen: {chosen}")
    cal = candidates[chosen]

    # Test metrics (uncalibrated baseline vs chosen).
    proba_uncal = best_pipe.predict_proba(X[te])
    proba_cal = cal.predict_proba(X[te])
    pred_cal = proba_cal.argmax(1)
    print("\n=== TEST (group-disjoint, leakage-free) ===")
    print(f"  top-1 acc        : {(pred_cal == y[te]).mean():.3f}")
    print(f"  top-3 acc        : {_topk_acc(proba_cal, y[te], 3):.3f}")
    print(f"  balanced acc     : {balanced_accuracy_score(y[te], pred_cal):.3f}")
    print(f"  ECE uncalibrated : {expected_calibration_error(proba_uncal, y[te]):.3f}")
    print(f"  ECE calibrated   : {expected_calibration_error(proba_cal, y[te]):.3f}")

    # Risk-coverage on validation → abstention threshold τ*.
    tau, cov = pick_threshold(cal.predict_proba(X[val]), y[val], args.target_acc)
    print(f"\nRisk-coverage (val): τ*={tau:.3f} keeps coverage={cov:.2f} "
          f"at selective_acc≥{args.target_acc}")
    print("  coverage / selective_acc curve (val):")
    for t, c, a in risk_coverage_curve(cal.predict_proba(X[val]), y[val])[::max(1, len(val)//8)]:
        print(f"    τ={t:.2f}  coverage={c:.2f}  sel_acc={a:.3f}")

    print("\nConfusion (test, rows=true):")
    cm = confusion_matrix(y[te], pred_cal, labels=list(range(len(STYLE_CLASSES))))
    print("  " + " ".join(f"{s[:4]:>4}" for s in STYLE_CLASSES))
    for i, row in enumerate(cm):
        print(f"  {STYLE_CLASSES[i][:4]:>4} " + " ".join(f"{v:>4}" for v in row))

    joblib.dump(cal, _OUT)
    print(f"\nSaved → {_OUT}")
    print(f"➡ Set in .env:  FUSER_MODEL_PATH=models/fuser.joblib   UNCERTAINTY_CONF_MIN={tau:.3f}")


if __name__ == "__main__":
    main()

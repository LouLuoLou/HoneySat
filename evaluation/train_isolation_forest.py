#!/usr/bin/env python3
"""Isolation Forest on telecommand CSVs with is_anomaly. Run from repo root; see evaluation/ML_README.md."""
from __future__ import annotations

import argparse
import re
import sys
import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from sklearn.ensemble import IsolationForest
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

try:
    import joblib
except ImportError:
    joblib = None  # type: ignore[misc, assignment]

# Ground-truth label column (from inject_anomalies output)
LABEL = "is_anomaly"
# Always-numeric columns we pass through before one-hot encoding pass_event
NUM_COLS = ["unix_timestamp", "norad_id", "ground_station_lat", "ground_station_lon"]


def slug_from_csv(path: Path) -> str:
    """Stem of CSV → safe suffix for plot/model filenames so runs do not clobber each other."""
    s = re.sub(r"[^a-zA-Z0-9_-]+", "_", path.stem).strip("_")
    return s or "dataset"


def build_X(df: pd.DataFrame) -> pd.DataFrame:
    """Build numeric design matrix: lat/lon/time/norad + one-hot pass_event; optional telecommand code."""
    missing = [c for c in NUM_COLS + ["pass_event"] if c not in df.columns]
    if missing:
        raise ValueError(f"CSV missing columns: {missing}")
    X = pd.get_dummies(
        df[NUM_COLS].assign(pass_event=df["pass_event"]),
        columns=["pass_event"],
        dtype=int,
    )
    if "telecommand" in df.columns and df["telecommand"].nunique() > 1:
        X["telecommand_enc"] = pd.factorize(df["telecommand"])[0]
    return X


def save_scatter(y_color: np.ndarray, ts_y: np.ndarray, title: str, path: Path) -> None:
    """Professor-style figure: test index vs timestamp, blue=normal red=anomaly."""
    c = np.where(y_color == 1, "red", "blue")
    plt.figure(figsize=(8, 4))
    plt.scatter(np.arange(len(y_color)), ts_y, c=c, s=40, alpha=0.85)
    plt.title(title)
    plt.xlabel("Test sample index")
    plt.ylabel("unix_timestamp")
    plt.legend(
        handles=[
            Line2D([0], [0], marker="o", color="w", markerfacecolor="blue", markersize=8, label="normal (0)"),
            Line2D([0], [0], marker="o", color="w", markerfacecolor="red", markersize=8, label="anomaly (1)"),
        ],
        title="Class",
        loc="best",
    )
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="Isolation Forest on telecommand anomaly CSV")
    ap.add_argument("--csv", default="telecommands_sample_100_anomalies.csv", help="Labeled CSV; run from repo root")
    ap.add_argument("--test-size", type=float, default=0.25)
    ap.add_argument("--random-state", type=int, default=42)
    ap.add_argument("--contamination", type=float, default=None, help="Else use train anomaly rate (clamped)")
    ap.add_argument("--run-tag", default=None, help="Override output filename tag (default: from CSV stem)")
    ap.add_argument("--output-dir", type=Path, default=Path("evaluation/outputs"))
    ap.add_argument("--n-estimators", type=int, default=200)
    ap.add_argument("--save-model", action=argparse.BooleanOptionalAction, default=True)
    a = ap.parse_args()

    csv_path = Path(a.csv)
    if not csv_path.is_file():
        print(f"File not found: {csv_path.resolve()}", file=sys.stderr)
        return 1
    run_tag = a.run_tag or slug_from_csv(csv_path)

    df = pd.read_csv(csv_path)
    df.columns = [str(c).strip() for c in df.columns]
    if LABEL not in df.columns:
        print(f"Missing '{LABEL}'. Use inject_anomalies output, not plain ground truth only.", file=sys.stderr)
        return 1
    y = df[LABEL].astype(int)
    if y.nunique() < 2:
        print("Need both classes in the file.", file=sys.stderr)
        return 1

    X = build_X(df)
    idx_all = np.arange(len(df))

    # Stratify keeps anomaly ratio similar in train/test when possible
    try:
        i_tr, i_te = train_test_split(
            idx_all, test_size=a.test_size, random_state=a.random_state, stratify=y
        )
    except ValueError as e:
        warnings.warn(f"Stratified split failed ({e}); using unstratified split.", UserWarning)
        i_tr, i_te = train_test_split(idx_all, test_size=a.test_size, random_state=a.random_state)

    X_tr, X_te = X.iloc[i_tr], X.iloc[i_te]
    y_tr, y_te = y.iloc[i_tr].reset_index(drop=True), y.iloc[i_te].reset_index(drop=True)
    ts_te = df.iloc[i_te]["unix_timestamp"].astype(np.int64).to_numpy()

    # Same scale as GFG example: fit scaler on train only
    scaler = StandardScaler()
    X_tr_s, X_te_s = scaler.fit_transform(X_tr), scaler.transform(X_te)

    # sklearn contamination must lie in (0, 0.5); default ≈ fraction of anomalies in y_tr
    if a.contamination is not None:
        contam = float(a.contamination)
    else:
        contam = min(max(float(y_tr.mean()), 1e-6), 0.49)

    clf = IsolationForest(
        n_estimators=a.n_estimators, contamination=contam, random_state=a.random_state
    )
    clf.fit(X_tr_s)

    # sklearn predict: 1 = inlier (normal), -1 = outlier → align with is_anomaly {0,1}
    y_pred = (clf.predict(X_te_s) == -1).astype(int)

    tn, fp, fn, tp = confusion_matrix(y_te, y_pred, labels=[0, 1]).ravel()
    print(f"CSV: {csv_path}\nOutput tag: {run_tag}\nTest size: {len(y_te)}  contamination: {contam:.6f}")
    print(f"accuracy:  {accuracy_score(y_te, y_pred):.4f}")
    print(f"precision: {precision_score(y_te, y_pred, zero_division=0):.4f}")
    print(f"recall:    {recall_score(y_te, y_pred, zero_division=0):.4f}")
    print(f"F1:        {f1_score(y_te, y_pred, zero_division=0):.4f}")
    print(f"confusion matrix [TN FP; FN TP]: {tn} {fp} {fn} {tp}")

    plot_dir = a.output_dir / "plots"
    model_dir = a.output_dir / "models"
    plot_dir.mkdir(parents=True, exist_ok=True)
    if a.save_model:
        model_dir.mkdir(parents=True, exist_ok=True)

    pred_png = plot_dir / f"iforest_pred_{run_tag}.png"
    true_png = plot_dir / f"iforest_true_{run_tag}.png"
    save_scatter(y_pred, ts_te, f"Isolation Forest: predicted (test) — {run_tag}", pred_png)
    save_scatter(y_te.to_numpy(), ts_te, f"Ground truth is_anomaly (test) — {run_tag}", true_png)
    print(f"Saved plots: {pred_png}, {true_png}")

    if a.save_model:
        if joblib is None:
            print("joblib not installed; skip model save.", file=sys.stderr)
        else:
            mp = model_dir / f"isolation_forest_{run_tag}.joblib"
            joblib.dump(
                {
                    "model": clf,
                    "scaler": scaler,
                    "feature_columns": list(X.columns),
                    "run_tag": run_tag,
                    "csv_path": str(csv_path),
                },
                mp,
            )
            print(f"Saved model: {mp}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
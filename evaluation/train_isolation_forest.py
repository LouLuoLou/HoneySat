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

# =============================================================================
# Constants
# =============================================================================
# Ground-truth column from inject_anomalies; never fed to IsolationForest.fit, only for metrics and plots.
LABEL = "is_anomaly"
# Norad and station coords are only used as features if the column exists and is not constant.
OPTIONAL_NUM_COLS = ("norad_id", "ground_station_lat", "ground_station_lon")


# =============================================================================
# Helpers: filenames and feature matrix
# =============================================================================
def slug_from_csv(path: Path) -> str:
    """Slug from CSV stem so plot and model files from different CSVs do not overwrite each other."""
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", path.stem).strip("_") or "dataset"


def build_X(df: pd.DataFrame) -> pd.DataFrame:
    """Features for the model: unix time, optional varying numeric cols, one-hot pass_event, telecommand codes."""
    miss = [c for c in ("unix_timestamp", "pass_event", "telecommand") if c not in df.columns]
    if miss:
        raise ValueError(f"CSV missing columns: {miss}")
    parts: dict[str, pd.Series] = {"unix_timestamp": pd.to_numeric(df["unix_timestamp"], errors="coerce")}
    for c in OPTIONAL_NUM_COLS:
        if c not in df.columns:
            continue
        col = pd.to_numeric(df[c], errors="coerce")
        if col.nunique(dropna=False) > 1:
            parts[c] = col
    out = pd.get_dummies(pd.DataFrame(parts).assign(pass_event=df["pass_event"]), columns=["pass_event"], dtype=int)
    if df["telecommand"].nunique() > 1:
        out["telecommand_enc"] = pd.factorize(df["telecommand"])[0]
    return out


def _class_legend_handles():
    """Blue and red dots for normal vs anomaly in scatter legends."""
    return [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=c, markersize=8, label=lab)
        for c, lab in (("blue", "normal (0)"), ("red", "anomaly (1)"))
    ]


# =============================================================================
# Plotting: test-set prediction vs truth (same x axis so you can compare side by side)
# =============================================================================
def save_scatter(y_color: np.ndarray, ts_y: np.ndarray, title: str, path: Path) -> None:
    """Each test row is one dot: x = row index in test set, y = unix_timestamp, color = class."""
    plt.figure(figsize=(8, 4))
    plt.scatter(np.arange(len(y_color)), ts_y, c=np.where(y_color == 1, "red", "blue"), s=40, alpha=0.85)
    plt.title(title)
    plt.xlabel("Test sample index")
    plt.ylabel("unix_timestamp")
    plt.legend(handles=_class_legend_handles(), title="Class", loc="best")
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()


# =============================================================================
# Train / test index split (stratify on label when possible)
# =============================================================================
def split_train_test_idx(y: pd.Series, test_size: float, random_state: int) -> tuple[np.ndarray, np.ndarray]:
    """Return row indices for training and held-out test; stratify keeps similar anomaly rate in both."""
    idx = np.arange(len(y))
    try:
        return train_test_split(idx, test_size=test_size, random_state=random_state, stratify=y)
    except ValueError as e:
        warnings.warn(f"Stratified split failed ({e}); using unstratified split.", UserWarning)
        return train_test_split(idx, test_size=test_size, random_state=random_state)


# =============================================================================
# Main pipeline
# =============================================================================
def main() -> int:
    # --- CLI: paths, split size, forest hyperparameters ---
    ap = argparse.ArgumentParser(description="Isolation Forest on telecommand anomaly CSV")
    ap.add_argument("--csv", default="telecommands_sample_100_anomalies.csv", help="Labeled CSV; run from repo root")
    ap.add_argument("--test-size", type=float, default=0.25)
    ap.add_argument("--random-state", type=int, default=42)
    ap.add_argument("--contamination", type=float, default=None, help="Else train anomaly rate (clamped)")
    ap.add_argument("--run-tag", default=None, help="Override output filename tag")
    ap.add_argument("--output-dir", type=Path, default=Path("evaluation/outputs"))
    ap.add_argument("--n-estimators", type=int, default=200)
    ap.add_argument("--save-model", action=argparse.BooleanOptionalAction, default=True)
    a = ap.parse_args()

    csv_path = Path(a.csv)
    if not csv_path.is_file():
        print(f"File not found: {csv_path.resolve()}", file=sys.stderr)
        return 1
    run_tag = a.run_tag or slug_from_csv(csv_path)

    # --- Load CSV and labels; labels are only for evaluation, not for clf.fit ---
    df = pd.read_csv(csv_path)
    df.columns = [str(c).strip() for c in df.columns]
    if LABEL not in df.columns:
        print(f"Missing '{LABEL}'. Use inject_anomalies output.", file=sys.stderr)
        return 1
    y = df[LABEL].astype(int)
    if y.nunique() < 2:
        print("Need both classes in the file.", file=sys.stderr)
        return 1

    # --- Build X (features only) and split rows into train vs test ---
    X = build_X(df)
    i_tr, i_te = split_train_test_idx(y, a.test_size, a.random_state)
    X_tr, X_te = X.iloc[i_tr], X.iloc[i_te]
    y_tr = y.iloc[i_tr].reset_index(drop=True)
    y_te = y.iloc[i_te].reset_index(drop=True)
    ts_te = df.iloc[i_te]["unix_timestamp"].astype(np.int64).to_numpy()

    # --- Scale features using training statistics only (avoid leakage from test) ---
    scaler = StandardScaler()
    X_tr_s, X_te_s = scaler.fit_transform(X_tr), scaler.transform(X_te)

    # --- Contamination = expected outlier fraction for sklearn, bounded to (0, 0.5) ---
    contam = float(a.contamination) if a.contamination is not None else min(max(float(y_tr.mean()), 1e-6), 0.49)

    # --- Train isolation forest on scaled training X only (unsupervised) ---
    clf = IsolationForest(n_estimators=a.n_estimators, contamination=contam, random_state=a.random_state)
    clf.fit(X_tr_s)

    # --- Predict on test: sklearn -1 means outlier; map to is_anomaly 1 ---
    y_pred = (clf.predict(X_te_s) == -1).astype(int)

    # --- Confusion matrix and scalar metrics vs held-out labels ---
    tn, fp, fn, tp = confusion_matrix(y_te, y_pred, labels=[0, 1]).ravel()
    zd = {"zero_division": 0}
    print(f"CSV: {csv_path}\nOutput tag: {run_tag}\nTest size: {len(y_te)}  contamination: {contam:.6f}")
    print(f"accuracy:  {accuracy_score(y_te, y_pred):.4f}")
    print(f"precision: {precision_score(y_te, y_pred, **zd):.4f}")
    print(f"recall:    {recall_score(y_te, y_pred, **zd):.4f}")
    print(f"F1:        {f1_score(y_te, y_pred, **zd):.4f}")
    print(f"confusion matrix [TN FP; FN TP]: {tn} {fp} {fn} {tp}")

    # --- Write PNGs: model guess vs CSV labels on the same test timestamps ---
    plot_dir, model_dir = a.output_dir / "plots", a.output_dir / "models"
    plot_dir.mkdir(parents=True, exist_ok=True)
    if a.save_model:
        model_dir.mkdir(parents=True, exist_ok=True)
    pred_png = plot_dir / f"iforest_pred_{run_tag}.png"
    true_png = plot_dir / f"iforest_true_{run_tag}.png"
    save_scatter(y_pred, ts_te, f"Isolation Forest: predicted (test) — {run_tag}", pred_png)
    save_scatter(y_te.to_numpy(), ts_te, f"Ground truth is_anomaly (test) — {run_tag}", true_png)
    print(f"Saved plots: {pred_png}, {true_png}")

    # --- Optional joblib bundle for later scoring without retraining ---
    if a.save_model and joblib is not None:
        mp = model_dir / f"isolation_forest_{run_tag}.joblib"
        joblib.dump(
            {"model": clf, "scaler": scaler, "feature_columns": list(X.columns), "run_tag": run_tag, "csv_path": str(csv_path)},
            mp,
        )
        print(f"Saved model: {mp}")
    elif a.save_model:
        print("joblib not installed; skip model save.", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
Train and evaluate sklearn IsolationForest on labeled telecommand CSVs (is_anomaly column).

Features (numeric after encoding):
  unix_timestamp, norad_id, ground_station_lat, ground_station_lon,
  one-hot columns for pass_event (rise / peak / set / mongo from get_dummies).

telecommand is omitted if constant across rows; otherwise label-encoded.

For reproducible research artifacts, get_dummies is applied before the split (fixed pass_event
vocabulary in our CSVs). For production, fit OneHotEncoder on train only.

Run from repository root:
  python3 evaluation/train_isolation_forest.py
  python3 evaluation/train_isolation_forest.py --csv telecommands_year_anomalies.csv
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

try:
    import joblib
except ImportError:
    joblib = None  # type: ignore[misc, assignment]


REQUIRED_LABEL_COL = "is_anomaly"
FEATURE_NUMERIC = [
    "unix_timestamp",
    "norad_id",
    "ground_station_lat",
    "ground_station_lon",
]


def build_feature_matrix(df: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in FEATURE_NUMERIC + ["pass_event"] if c not in df.columns]
    if missing:
        raise ValueError(f"CSV missing columns: {missing}")

    base = df[FEATURE_NUMERIC].copy()
    X = pd.get_dummies(base.assign(pass_event=df["pass_event"]), columns=["pass_event"], dtype=int)

    if "telecommand" in df.columns and df["telecommand"].nunique() > 1:
        X["telecommand_enc"] = pd.factorize(df["telecommand"])[0]

    return X


def isolation_to_binary(raw: np.ndarray) -> np.ndarray:
    """sklearn: 1 = inlier (normal), -1 = outlier (anomaly) -> 0 = normal, 1 = anomaly."""
    out = np.zeros(len(raw), dtype=int)
    out[raw == -1] = 1
    return out


def train_contamination(y_train: pd.Series, override: float | None) -> float:
    if override is not None:
        return float(override)
    rate = float(y_train.mean())
    return min(max(rate, 1e-6), 0.49)


def main() -> int:
    p = argparse.ArgumentParser(description="Isolation Forest on telecommand anomaly CSV")
    p.add_argument(
        "--csv",
        default="telecommands_sample_100_anomalies.csv",
        help="Path to CSV with is_anomaly (default: sample file; run from repo root)",
    )
    p.add_argument("--test-size", type=float, default=0.25)
    p.add_argument("--random-state", type=int, default=42)
    p.add_argument(
        "--contamination",
        type=float,
        default=None,
        help="Override IF contamination; default = training-set anomaly rate (clamped)",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=Path("evaluation/outputs"),
        help="Writes plots/ and models/ under this directory",
    )
    p.add_argument("--n-estimators", type=int, default=200)
    p.add_argument(
        "--save-model",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Save fitted model with joblib (use --no-save-model to skip)",
    )
    args = p.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.is_file():
        print(f"File not found: {csv_path.resolve()}", file=sys.stderr)
        return 1

    df = pd.read_csv(csv_path)
    df.columns = [str(c).strip() for c in df.columns]

    if REQUIRED_LABEL_COL not in df.columns:
        print(
            f"Column '{REQUIRED_LABEL_COL}' missing (ground-truth-only CSV?). "
            f"Use a file from inject_anomalies, e.g. telecommands_sample_100_anomalies.csv",
            file=sys.stderr,
        )
        return 1

    y = df[REQUIRED_LABEL_COL].astype(int)
    if y.nunique() < 2:
        print("Need both normal and anomaly rows in the CSV for evaluation.", file=sys.stderr)
        return 1

    X = build_feature_matrix(df)
    indices = np.arange(len(df))

    stratify = y
    try:
        idx_train, idx_test = train_test_split(
            indices,
            test_size=args.test_size,
            random_state=args.random_state,
            stratify=stratify,
        )
    except ValueError as e:
        warnings.warn(f"Stratified split failed ({e}); using random split.", UserWarning)
        idx_train, idx_test = train_test_split(
            indices,
            test_size=args.test_size,
            random_state=args.random_state,
        )

    X_train, X_test = X.iloc[idx_train], X.iloc[idx_test]
    y_train, y_test = y.iloc[idx_train].reset_index(drop=True), y.iloc[idx_test].reset_index(drop=True)
    ts_test = df.iloc[idx_test]["unix_timestamp"].astype(np.int64).to_numpy()

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    contam = train_contamination(y_train, args.contamination)
    clf = IsolationForest(
        n_estimators=args.n_estimators,
        contamination=contam,
        random_state=args.random_state,
    )
    clf.fit(X_train_s)

    raw_pred = clf.predict(X_test_s)
    y_pred = isolation_to_binary(raw_pred)

    acc = accuracy_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred, zero_division=0)
    rec = recall_score(y_test, y_pred, zero_division=0)
    f1 = f1_score(y_test, y_pred, zero_division=0)
    cm = confusion_matrix(y_test, y_pred, labels=[0, 1])
    tn, fp, fn, tp = cm.ravel()

    print(f"CSV: {csv_path}")
    print(f"Test size: {len(y_test)}  contamination (used): {contam:.6f}")
    print(f"accuracy:  {acc:.4f}")
    print(f"precision: {prec:.4f}")
    print(f"recall:    {rec:.4f}")
    print(f"F1:        {f1:.4f}")
    print(f"confusion matrix [TN FP; FN TP]: {tn} {fp} {fn} {tp}")

    out_dir = args.output_dir
    plot_dir = out_dir / "plots"
    model_dir = out_dir / "models"
    plot_dir.mkdir(parents=True, exist_ok=True)
    if args.save_model:
        model_dir.mkdir(parents=True, exist_ok=True)

    x_axis = np.arange(len(y_test))

    def scatter_pred(true_or_pred: np.ndarray, title: str, path: Path) -> None:
        colors = np.where(true_or_pred == 1, "red", "blue")
        plt.figure(figsize=(8, 4))
        plt.scatter(x_axis, ts_test, c=colors, s=40, alpha=0.85)
        plt.title(title)
        plt.xlabel("Test sample index")
        plt.ylabel("unix_timestamp")
        from matplotlib.lines import Line2D

        legend_elems = [
            Line2D([0], [0], marker="o", color="w", markerfacecolor="blue", markersize=8, label="normal (0)"),
            Line2D([0], [0], marker="o", color="w", markerfacecolor="red", markersize=8, label="anomaly (1)"),
        ]
        plt.legend(handles=legend_elems, title="Class", loc="best")
        plt.tight_layout()
        plt.savefig(path, dpi=150)
        plt.close()

    scatter_pred(
        y_pred,
        "Isolation Forest: predicted normal vs anomaly (test set)",
        plot_dir / "iforest_pred.png",
    )
    scatter_pred(
        y_test.to_numpy(),
        "Ground truth is_anomaly (test set)",
        plot_dir / "iforest_true.png",
    )
    print(f"Saved plots: {plot_dir / 'iforest_pred.png'}, {plot_dir / 'iforest_true.png'}")

    if args.save_model:
        if joblib is None:
            print("joblib not installed; skip model save.", file=sys.stderr)
        else:
            bundle = {"model": clf, "scaler": scaler, "feature_columns": list(X.columns)}
            model_path = model_dir / "isolation_forest.joblib"
            joblib.dump(bundle, model_path)
            print(f"Saved model: {model_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

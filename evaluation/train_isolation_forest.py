#!/usr/bin/env python3
"""Train and evaluate an Isolation Forest on labeled telecommand anomaly CSVs."""
from __future__ import annotations

# ── Imports ──────────────────────────────────────────────────────────────────
import argparse, re, sys, warnings
from pathlib import Path

import matplotlib.dates as mdates
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

# ── Constants ────────────────────────────────────────────────────────────────
LABEL = "is_anomaly"
PASS_POSITION = {"rise": 0.0, "peak": 0.5, "set": 1.0, "mongo": 0.25}

# ── Helpers ──────────────────────────────────────────────────────────────────

def slug_from_csv(path: Path) -> str:
    """Turn a CSV filename into a safe string for plot/model filenames."""
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", path.stem).strip("_") or "dataset"

def rolling_count(sorted_times: np.ndarray, window_sec: int) -> np.ndarray:
    """Count how many commands happened in the last `window_sec` seconds before each row."""
    counts = np.zeros(len(sorted_times), dtype=float)
    left = 0
    for right, t in enumerate(sorted_times):
        while t - sorted_times[left] > window_sec:
            left += 1
        counts[right] = float(right - left)
    return counts

# ── Feature engineering ──────────────────────────────────────────────────────
# Each CSV row becomes one feature vector. We never feed the raw
# unix_timestamp or is_anomaly label to the model.

def build_features(table: pd.DataFrame) -> pd.DataFrame:
    """Build all model features from the labeled anomaly CSV."""
    required = ("unix_timestamp", "telecommand", "pass_event")
    missing = [c for c in required if c not in table.columns]
    if missing:
        raise ValueError(f"CSV missing columns: {missing}")

    # Sort by time so "since previous" calculations are correct.
    df = table.copy()
    df["_row"] = table.index
    df["_unix"] = pd.to_numeric(df["unix_timestamp"], errors="coerce")
    df = df.sort_values("_unix", kind="stable")
    utc = pd.to_datetime(df["_unix"], unit="s", utc=True)

    # Basic time-of-day and day-of-week features.
    df["hour_utc"] = utc.dt.hour.fillna(0).astype(float)
    df["day_of_week_utc"] = utc.dt.dayofweek.fillna(0).astype(float)

    # Cyclical encoding: sin/cos lets the model know that hour 23 and hour 0
    # are neighbors, not 23 apart. Same idea for day of week.
    df["hour_sin"] = np.sin(2 * np.pi * df["hour_utc"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour_utc"] / 24)
    df["dow_sin"] = np.sin(2 * np.pi * df["day_of_week_utc"] / 7)
    df["dow_cos"] = np.cos(2 * np.pi * df["day_of_week_utc"] / 7)

    # Time gaps — these are the strongest anomaly signal.
    df["seconds_since_prev"] = df["_unix"].diff().clip(lower=0).fillna(0.0)
    df["seconds_since_same_command"] = (
        df.groupby("telecommand")["_unix"].diff().clip(lower=0).fillna(0.0))

    # Burstiness: how crowded is the recent timeline?
    df["recent_10min_count"] = rolling_count(df["_unix"].to_numpy(), 600)

    # Pass position: rise=0, peak=0.5, set=1.
    df["pass_position"] = df["pass_event"].map(PASS_POSITION).fillna(-1.0).astype(float)

    feat_cols = [
        "hour_utc", "day_of_week_utc",
        "hour_sin", "hour_cos", "dow_sin", "dow_cos",
        "seconds_since_prev", "seconds_since_same_command",
        "recent_10min_count", "pass_position",
    ]
    features = df[feat_cols].copy()

    # One-hot encode the pass phase for extra context.
    features = pd.get_dummies(
        features.assign(pass_event=df["pass_event"]),
        columns=["pass_event"], dtype=int)

    # Numeric id for each unique telecommand string.
    if df["telecommand"].nunique() > 1:
        features["telecommand_enc"] = pd.factorize(df["telecommand"])[0]

    # Restore original row order so indices match the rest of the pipeline.
    features.index = df["_row"]
    return features.reindex(table.index).fillna(0)

# ── Train / test split ───────────────────────────────────────────────────────

def split_train_test(labels: pd.Series, test_size: float, seed: int):
    """Stratified split that falls back to unstratified if a class is too small."""
    rows = np.arange(len(labels))
    try:
        return train_test_split(rows, test_size=test_size, random_state=seed, stratify=labels)
    except ValueError as e:
        warnings.warn(f"Stratified split failed ({e}); using unstratified.", UserWarning)
        return train_test_split(rows, test_size=test_size, random_state=seed)

# ── Plotting ─────────────────────────────────────────────────────────────────
# One clean scatter per PNG: x = UTC time, y = seconds since previous command.
# Normal points are small and faded; anomaly points are large and bold.
# Legend sits below the plot so it never covers any data.

NORMAL_COLOR = "cadetblue"
ANOMALY_COLOR = "tomato"

def _legend_handles():
    return [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=NORMAL_COLOR,
               markersize=8, label="Normal"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=ANOMALY_COLOR,
               markersize=8, label="Anomaly"),
    ]

def save_plot(classes, timestamps, gaps, title: str, out: Path) -> None:
    """Save a single time-vs-gap scatter plot colored by class."""
    order = np.argsort(timestamps)
    times = pd.to_datetime(timestamps[order], unit="s", utc=True).tz_localize(None)
    cls = classes[order]
    gap = np.maximum(gaps[order], 0.5)

    fig, ax = plt.subplots(figsize=(8, 4.2))
    norm = cls == 0
    anom = cls == 1

    # Draw normal points first so anomalies sit on top.
    ax.scatter(times[norm], gap[norm], color=NORMAL_COLOR, s=42, alpha=0.45, edgecolors="none")
    ax.scatter(times[anom], gap[anom], color=ANOMALY_COLOR, s=85, alpha=0.95,
               edgecolors="white", linewidths=0.5)

    ax.set_title(title)
    ax.set_xlabel("UTC time")
    ax.set_ylabel("Seconds since previous command")
    ax.set_yscale("log")
    ax.grid(True, linestyle="--", alpha=0.18)

    loc = mdates.AutoDateLocator()
    ax.xaxis.set_major_locator(loc)
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(loc))

    # Legend below the plot, centered, no border.
    fig.legend(handles=_legend_handles(), loc="upper center",
               bbox_to_anchor=(0.5, -0.01), ncol=2, frameon=False)
    fig.tight_layout(rect=[0, 0.05, 1, 1])
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)

# ── Main pipeline ────────────────────────────────────────────────────────────

def main() -> int:
    # --- Parse CLI arguments ---
    p = argparse.ArgumentParser(description="Isolation Forest on telecommand anomaly CSV")
    p.add_argument("--csv", default="evaluation/outputs/anomalies/telecommands_sample_100_anomalies.csv",
                   help="Labeled CSV; run from repo root")
    p.add_argument("--test-size", type=float, default=0.25)
    p.add_argument("--random-state", type=int, default=42)
    p.add_argument("--contamination", type=float, default=None, help="Else use train anomaly rate")
    p.add_argument("--run-tag", default=None, help="Override output filename tag")
    p.add_argument("--output-dir", type=Path, default=Path("evaluation/outputs"))
    p.add_argument("--n-estimators", type=int, default=200)
    p.add_argument("--save-model", action=argparse.BooleanOptionalAction, default=True)
    args = p.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.is_file():
        print(f"File not found: {csv_path.resolve()}", file=sys.stderr)
        return 1
    run_tag = args.run_tag or slug_from_csv(csv_path)

    # --- Load CSV ---
    table = pd.read_csv(csv_path)
    table.columns = [str(c).strip() for c in table.columns]
    if LABEL not in table.columns:
        print(f"Missing '{LABEL}'. Use inject_anomalies output.", file=sys.stderr)
        return 1
    labels = table[LABEL].astype(int)
    if labels.nunique() < 2:
        print("Need both classes in the file.", file=sys.stderr)
        return 1

    # --- Build features and split ---
    features = build_features(table)
    train_idx, test_idx = split_train_test(labels, args.test_size, args.random_state)
    x_train, x_test = features.iloc[train_idx], features.iloc[test_idx]
    y_train = labels.iloc[train_idx].reset_index(drop=True)
    y_test = labels.iloc[test_idx].reset_index(drop=True)

    # Keep raw values for plotting (not fed to the model).
    plot_times = table.iloc[test_idx]["unix_timestamp"].astype(np.int64).to_numpy()
    plot_gaps = features.iloc[test_idx]["seconds_since_prev"].astype(float).to_numpy()

    # --- Scale features ---
    scaler = StandardScaler()
    x_train_s = scaler.fit_transform(x_train)
    x_test_s = scaler.transform(x_test)

    # --- Train Isolation Forest ---
    contamination = (float(args.contamination) if args.contamination is not None
                     else min(max(float(y_train.mean()), 1e-6), 0.49))
    model = IsolationForest(n_estimators=args.n_estimators,
                            contamination=contamination,
                            random_state=args.random_state)
    model.fit(x_train_s)

    # sklearn returns -1 for outlier, +1 for normal. Map to 1/0 like the CSV.
    preds = (model.predict(x_test_s) == -1).astype(int)

    # --- Print metrics ---
    tn, fp, fn, tp = confusion_matrix(y_test, preds, labels=[0, 1]).ravel()
    zd = {"zero_division": 0}
    print(f"CSV: {csv_path}\nOutput tag: {run_tag}\nTest size: {len(y_test)}  contamination: {contamination:.6f}")
    print(f"accuracy:  {accuracy_score(y_test, preds):.4f}")
    print(f"precision: {precision_score(y_test, preds, **zd):.4f}")
    print(f"recall:    {recall_score(y_test, preds, **zd):.4f}")
    print(f"F1:        {f1_score(y_test, preds, **zd):.4f}")
    print(f"confusion matrix [TN FP; FN TP]: {tn} {fp} {fn} {tp}")

    # --- Save plots ---
    plot_dir = args.output_dir / "plots"
    model_dir = args.output_dir / "models"
    plot_dir.mkdir(parents=True, exist_ok=True)

    save_plot(preds, plot_times, plot_gaps,
              f"Isolation Forest: predicted (test) — {run_tag}",
              plot_dir / f"iforest_pred_{run_tag}.png")
    save_plot(y_test.to_numpy(), plot_times, plot_gaps,
              f"Ground truth is_anomaly (test) — {run_tag}",
              plot_dir / f"iforest_true_{run_tag}.png")
    print(f"Saved plots: {plot_dir / f'iforest_pred_{run_tag}.png'}, "
          f"{plot_dir / f'iforest_true_{run_tag}.png'}")

    # --- Save model ---
    if args.save_model:
        model_dir.mkdir(parents=True, exist_ok=True)
        if joblib is not None:
            path = model_dir / f"isolation_forest_{run_tag}.joblib"
            joblib.dump({"model": model, "scaler": scaler,
                         "feature_columns": list(features.columns),
                         "run_tag": run_tag, "csv_path": str(csv_path)}, path)
            print(f"Saved model: {path}")
        else:
            print("joblib not installed; skip model save.", file=sys.stderr)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

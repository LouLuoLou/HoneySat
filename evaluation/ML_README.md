# Telecommand anomaly detection (Isolation Forest)

Optional demo: train scikit-learn `IsolationForest` on labeled CSVs produced by `inject_anomalies.py`
(`is_anomaly` column required). Outputs plots and an optional saved model under `evaluation/outputs/`
(gitignored).

## Setup

From the **repository root**:

```bash
python3 -m venv .
source bin/activate
python3 -m pip install -r evaluation/requirements.txt
```

## Run (quick sample)

Default CSV is `telecommands_sample_100_anomalies.csv` in the repo root:

```bash
python3 evaluation/train_isolation_forest.py
```

## Run (full year)

```bash
python3 evaluation/train_isolation_forest.py --csv telecommands_year_anomalies.csv
```

## Outputs

File names include a **tag** from the CSV filename stem so the 100-row and year runs do not overwrite each other.

Examples:

- Sample CSV → `iforest_pred_telecommands_sample_100_anomalies.png`, `iforest_true_telecommands_sample_100_anomalies.png`, `isolation_forest_telecommands_sample_100_anomalies.joblib`
- Year CSV → `iforest_pred_telecommands_year_anomalies.png`, …, `isolation_forest_telecommands_year_anomalies.joblib`

## Useful flags

- `--run-tag myname` — override the tag used in output filenames (default: slug from `--csv` stem)
- `--test-size 0.25` — holdout fraction
- `--contamination 0.05` — override Isolation Forest contamination (default: anomaly rate on training split)
- `--output-dir evaluation/outputs` — change output root
- `--no-save-model` — skip joblib dump

`telecommands_dataset.csv` has no `is_anomaly` column; use a labeled anomalies file only.

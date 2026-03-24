#!/usr/bin/env python3
"""
Build a 1-year telecommand dataset (CSV) from HoneySat MongoDB logs.

Prerequisites
-------------
- CSP (or any) stack running with ``logs_mongodb`` publishing port 27017 to the host.
- Python venv with ``pymongo`` (see ``evaluation/requirements.txt``).

Usage (from repository root)::

    source bin/activate   # if using repo-root venv
    python3 evaluation/extrapolate_telecommands_dataset.py --output telecommands_1year.csv

Options::

    --host localhost --port 27017
    --dry-run              # print counts only, no CSV
    --num-synthetic N      # add exactly N synthetic timestamps (still merges real rows in window)
    --min-rows 10000       # default target minimum rows if --num-synthetic not set
    --spacing uniform      # or poisson (inter-arrival from real events, else default)

Environment (optional overrides)::

    MONGO_HOST, MONGO_PORT

Fixed metadata (assignment / analysis): NORAD 62171, ground station El Paso, TX
(lat 31.7619, lon -106.4850) — same on every output row.

Data source: collection ``TelnetMessageRecieved`` in database ``honeysat_log``.
Documents use a JSON string field ``data`` with a ``message`` key (telnet input).
Only documents whose message contains ``com_ping`` are used as real seed events.
Synthetic rows use telecommand ``1: com_ping 10``.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, List, Sequence, Tuple

try:
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure, OperationFailure
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "pymongo is required. Install with: pip install -r evaluation/requirements.txt"
    ) from exc

# ---------------------------------------------------------------------------
# Credentials mirror evaluation/experiment-1/python_dump_mongodb/dump_mongodb.py
MONGO_USER = "honeysat_root_1"
MONGO_PASS = "honeysat_rootpass_1234"
MONGO_DB = "honeysat_log"
COLLECTION = "TelnetMessageRecieved"

# Fixed metadata: NORAD catalog + El Paso, TX (same for all datapoints)
NORAD_ID = 62171
GROUND_STATION_LAT = 31.7619
GROUND_STATION_LON = -106.4850
CANONICAL_TELECOMMAND = "1: com_ping 10"


def to_unix_utc(dt: datetime) -> int:
    """Convert stored datetime to Unix seconds in UTC (naive datetimes treated as UTC)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return int(dt.timestamp())


def build_uri(host: str, port: int) -> str:
    return (
        f"mongodb://{MONGO_USER}:{MONGO_PASS}@{host}:{port}/{MONGO_DB}"
        f"?authSource=admin"
    )


def fetch_real_events(
    collection: Any,
    window_start: datetime,
    window_end: datetime,
) -> List[Tuple[int, str]]:
    """
    Return list of (unix_ts, telecommand) for com_ping-related telnet messages
    whose time falls in [window_start, window_end] (UTC).
    Output telecommand is canonical ``1: com_ping 10`` for consistency.
    """
    ws = window_start
    we = window_end
    if ws.tzinfo is None:
        ws = ws.replace(tzinfo=timezone.utc)
    if we.tzinfo is None:
        we = we.replace(tzinfo=timezone.utc)

    out: List[Tuple[int, str]] = []
    for doc in collection.find({}):
        raw_time = doc.get("time")
        if not isinstance(raw_time, datetime):
            continue
        t = raw_time
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        else:
            t = t.astimezone(timezone.utc)
        if not (ws <= t <= we):
            continue
        data_raw = doc.get("data")
        if data_raw is None:
            continue
        if isinstance(data_raw, dict):
            payload = data_raw
        else:
            try:
                payload = json.loads(data_raw)
            except (json.JSONDecodeError, TypeError) as e:
                print(f"Warning: skip doc {doc.get('_id')}: invalid JSON in data: {e}", file=sys.stderr)
                continue
        message = payload.get("message")
        if not isinstance(message, str) or "com_ping" not in message:
            continue
        out.append((to_unix_utc(raw_time), CANONICAL_TELECOMMAND))
    out.sort(key=lambda x: x[0])
    return out


def mean_interarrival_seconds(timestamps: Sequence[int]) -> float:
    """Mean gap between sorted unique timestamps; default if insufficient data."""
    if len(timestamps) < 2:
        return 300.0  # 5 minutes default for Poisson spacing
    ts = sorted(set(timestamps))
    gaps = [ts[i + 1] - ts[i] for i in range(len(ts) - 1)]
    if not gaps:
        return 300.0
    return max(1.0, sum(gaps) / len(gaps))


def generate_synthetic_uniform(
    t_start: int,
    t_end: int,
    n: int,
    rng: random.Random,
) -> List[int]:
    if n <= 0:
        return []
    return sorted(rng.randint(t_start, t_end) for _ in range(n))


def generate_synthetic_poisson(
    t_start: int,
    t_end: int,
    n: int,
    mean_gap: float,
    rng: random.Random,
) -> List[int]:
    """Generate ~n event times via exponential inter-arrival, clipped to window."""
    if n <= 0 or t_end <= t_start:
        return []
    out: List[int] = []
    rate = 1.0 / mean_gap
    t = float(t_start)
    while len(out) < n * 3 and t < t_end:  # oversample then trim
        gap = rng.expovariate(rate)
        t += gap
        if t_start <= t <= t_end:
            out.append(int(t))
    rng.shuffle(out)
    out = sorted(set(out))[:n]
    while len(out) < n:
        out.append(rng.randint(t_start, t_end))
    out.sort()
    return out[:n]


def merge_rows(
    real: List[Tuple[int, str]],
    synthetic_ts: List[int],
    telecommand: str,
) -> List[Tuple[int, str]]:
    rows: List[Tuple[int, str]] = list(real)
    for ts in synthetic_ts:
        rows.append((ts, telecommand))
    rows.sort(key=lambda x: x[0])
    # Deduplicate same second: keep first, bump duplicates by +1 second if needed
    deduped: List[Tuple[int, str]] = []
    seen: set[int] = set()
    for ts, cmd in rows:
        while ts in seen:
            ts += 1
        seen.add(ts)
        deduped.append((ts, cmd))
    return deduped


def write_csv(
    path: str,
    rows: List[Tuple[int, str]],
) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "unix_timestamp",
                "telecommand",
                "norad_id",
                "ground_station_lat",
                "ground_station_lon",
            ]
        )
        for ts, cmd in rows:
            w.writerow(
                [
                    ts,
                    cmd,
                    NORAD_ID,
                    GROUND_STATION_LAT,
                    GROUND_STATION_LON,
                ]
            )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Extrapolate 1-year telecommand CSV from HoneySat MongoDB logs."
    )
    p.add_argument(
        "--output",
        "-o",
        default="telecommands_1year.csv",
        help="Output CSV path (default: telecommands_1year.csv)",
    )
    p.add_argument(
        "--host",
        default=os.environ.get("MONGO_HOST", "localhost"),
        help="MongoDB host (default: localhost or MONGO_HOST)",
    )
    p.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("MONGO_PORT", "27017")),
        help="MongoDB port (default: 27017 or MONGO_PORT)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print summary only; do not write CSV",
    )
    p.add_argument(
        "--num-synthetic",
        type=int,
        default=None,
        metavar="N",
        help="Exact number of synthetic timestamps to add (in addition to real rows in window)",
    )
    p.add_argument(
        "--min-rows",
        type=int,
        default=10000,
        help="Minimum total rows when --num-synthetic is omitted (default: 10000)",
    )
    p.add_argument(
        "--spacing",
        choices=("uniform", "poisson"),
        default="uniform",
        help="Synthetic timestamp spacing (default: uniform)",
    )
    p.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducible synthetic data",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    rng = random.Random(args.seed)

    window_end = datetime.now(timezone.utc)
    window_start = window_end - timedelta(days=365)
    t_start = int(window_start.timestamp())
    t_end = int(window_end.timestamp())

    uri = build_uri(args.host, args.port)
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=8000)
        client.admin.command("ping")
    except ConnectionFailure as e:
        print(f"Could not connect to MongoDB at {args.host}:{args.port}: {e}", file=sys.stderr)
        return 1
    except OperationFailure as e:
        print(f"MongoDB authentication failed: {e}", file=sys.stderr)
        return 1

    coll = client[MONGO_DB][COLLECTION]
    real = fetch_real_events(coll, window_start, window_end)

    if args.num_synthetic is not None:
        n_synth = max(0, args.num_synthetic)
    else:
        n_synth = max(0, args.min_rows - len(real))

    mean_gap = mean_interarrival_seconds([r[0] for r in real])
    if args.spacing == "uniform":
        synthetic_ts = generate_synthetic_uniform(t_start, t_end, n_synth, rng)
    else:
        synthetic_ts = generate_synthetic_poisson(t_start, t_end, n_synth, mean_gap, rng)

    rows = merge_rows(real, synthetic_ts, CANONICAL_TELECOMMAND)

    print(
        f"Window (UTC): {window_start.isoformat()} .. {window_end.isoformat()}\n"
        f"Real com_ping events in window: {len(real)}\n"
        f"Synthetic timestamps added: {len(synthetic_ts)}\n"
        f"Total rows after merge/dedup: {len(rows)}\n"
        f"NORAD={NORAD_ID}, ground_station=({GROUND_STATION_LAT}, {GROUND_STATION_LON})"
    )

    if args.dry_run:
        return 0

    write_csv(args.output, rows)
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Create labeled anomaly CSVs from the base telecommand dataset.

Flow:
1. Load telecommands_dataset.csv (or build it via dataset_telecommands.py).
2. Pick a small percentage of rows and turn them into anomaly bursts.
3. Write two labeled CSVs: a small sample and a full-year version.

Every anomaly lives inside a short time burst (5-10 consecutive seconds).
Some bursts also swap the telecommand to an unusual one for extra variety.
"""
from __future__ import annotations

# ── Imports ──────────────────────────────────────────────────────────────────
import argparse, csv, os, random, subprocess, sys, tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import requests
from skyfield.api import EarthSatellite, load, wgs84

# ── Constants ────────────────────────────────────────────────────────────────
# Columns present in the raw dataset (includes metadata used for pass calc).
INPUT_COLS = (
    "unix_timestamp", "telecommand", "norad_id",
    "ground_station_lat", "ground_station_lon", "pass_event",
)
# Columns written to the output anomaly CSVs (metadata stripped for ML).
OUTPUT_COLS = ("unix_timestamp", "telecommand", "pass_event", "is_anomaly")

NORMAL_COMMAND = "1: com_ping 10"
ANOMALY_COMMANDS = (
    "1: sen_get_temp 10", "1: obc_update_status 10", "1: eps_get_hk 10",
    "1: eps_update_status 10", "1: sen_get_eps 10", "1: eps_set_output 10",
    "1: eps_set_output_all 10", "1: eps_set_heater 10", "1: eps_hard_reset 10",
)

# ── File loading ─────────────────────────────────────────────────────────────
def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent

def run_ground_truth_script(root: Path, out_csv: Path, days: int, no_mongo: bool) -> None:
    """Call dataset_telecommands.py to build a fresh base CSV from scratch."""
    cmd = [sys.executable, str(root / "evaluation" / "dataset_telecommands.py"),
           "-o", str(out_csv), "--days", str(days)]
    if no_mongo:
        cmd.append("--no-mongo")
    subprocess.run(cmd, cwd=root, check=True)

def load_rows(path: Path) -> list[dict[str, str]]:
    """Read the base CSV and verify it has the expected columns."""
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("empty CSV")
        names = [n.strip() for n in reader.fieldnames]
        if names != list(INPUT_COLS):
            raise ValueError(f"expected columns {list(INPUT_COLS)}, got {names}")
        return [dict(row) for row in reader]

# ── Satellite pass helpers ───────────────────────────────────────────────────
# These functions figure out when the satellite is visible so we can place
# anomalies just outside those windows (making them look suspicious).

def _to_unix(t) -> int:
    dt = t.utc_datetime()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())

def merged_pass_intervals(
    norad: int, lat: float, lon: float, elev_m: float,
    start: datetime, end: datetime,
) -> list[tuple[int, int]]:
    """Fetch TLE from CelesTrak, compute visible passes, merge overlapping ones."""
    resp = requests.get(
        f"https://celestrak.org/NORAD/elements/gp.php?CATNR={norad}&FORMAT=TLE",
        timeout=45)
    resp.raise_for_status()
    lines = [l.strip() for l in resp.text.strip().splitlines() if l.strip()]
    if len(lines) < 3:
        raise ValueError(f"No TLE for NORAD {norad}")

    ts = load.timescale()
    sat = EarthSatellite(lines[1], lines[2], lines[0], ts)
    obs = wgs84.latlon(lat, lon, elevation_m=elev_m)
    times, events = sat.find_events(
        obs, ts.from_datetime(start), ts.from_datetime(end), altitude_degrees=10.0)

    # Group rise(0)-peak(1)-set(2) triplets into (start, end) intervals.
    codes = [int(c) for c in events]
    raw: list[tuple[int, int]] = []
    i = 0
    while i + 2 < len(codes):
        if codes[i] == 0 and codes[i+1] == 1 and codes[i+2] == 2:
            raw.append((_to_unix(times[i]), _to_unix(times[i+2])))
            i += 3
        else:
            i += 1
    if not raw:
        return []

    # Merge touching intervals so we don't double-count.
    raw.sort()
    merged = [raw[0]]
    for lo, hi in raw[1:]:
        if lo <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    return merged

def gap_intervals(start: int, end: int, passes: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Return time ranges between visible passes (where the sat is NOT visible)."""
    if not passes:
        return [(start, end)]
    gaps: list[tuple[int, int]] = []
    cur = start
    for lo, hi in passes:
        lo, hi = max(lo, start), min(hi, end)
        if cur < lo:
            gaps.append((cur, lo - 1))
        cur = max(cur, hi + 1)
    if cur <= end:
        gaps.append((cur, end))
    return [(a, b) for a, b in gaps if a <= b]

def edge_windows(gaps: list[tuple[int, int]], burst_size: int, edge_sec: int = 900) -> list[tuple[int, int]]:
    """Keep only the first/last few minutes of each gap for subtle anomaly placement."""
    out: list[tuple[int, int]] = []
    for lo, hi in gaps:
        w = hi - lo + 1
        if w < burst_size:
            continue
        e = min(edge_sec, w)
        left = (lo, min(hi, lo + e - 1))
        right = (max(lo, hi - e + 1), hi)
        out.append(left)
        if right != left:
            out.append(right)
    return out

# ── Anomaly planning ────────────────────────────────────────────────────────
# Decide how many anomalies, how big each burst is, and where to put them.

def rare_utc_hours(unix_times: list[int], take: int = 4) -> set[int]:
    """Find the least-common UTC hours in the dataset so anomalies land at odd times."""
    hours = [datetime.fromtimestamp(t, tz=timezone.utc).hour for t in unix_times]
    ordered = sorted(Counter(hours).items(), key=lambda x: (x[1], x[0]))
    return {h for h, _ in ordered[:max(1, min(take, len(ordered)))]}

def plan_bursts(rng: random.Random, total: int, bmin: int, bmax: int) -> list[int]:
    """Split the anomaly count into burst sizes, never leaving a tiny leftover."""
    if total <= 0:
        return []
    if total <= bmax:
        return [total]
    bursts: list[int] = []
    left = total
    while left > bmax:
        s = rng.randint(bmin, bmax)
        if left - s < bmin:
            s = left - bmin
        bursts.append(s)
        left -= s
    bursts.append(left)
    return bursts

def pick_burst_start(
    rng: random.Random, windows: list[tuple[int, int]], size: int,
    occupied: set[int], hours: set[int] | None = None, tries: int = 80,
) -> int | None:
    """Try to find a consecutive run of `size` free seconds inside one window."""
    valid = [(lo, hi) for lo, hi in windows if hi - lo + 1 >= size]
    if not valid:
        return None
    rng.shuffle(valid)
    for lo, hi in valid:
        for _ in range(tries):
            start = rng.randint(lo, hi - size + 1)
            if hours and datetime.fromtimestamp(start, tz=timezone.utc).hour not in hours:
                continue
            if all((start + k) not in occupied for k in range(size)):
                return start
    return None

# ── Anomaly assignment ──────────────────────────────────────────────────────

def assign_time_anomaly(rows, picked, gap_edges, occupied, rare_hrs, rng) -> None:
    """Move a group of rows to consecutive seconds just outside a visible pass."""
    n = len(picked)
    start = pick_burst_start(rng, gap_edges, n, occupied, hours=rare_hrs)
    if start is None:
        start = pick_burst_start(rng, gap_edges, n, occupied)
    if start is None:
        raise ValueError("could not place time anomaly burst")
    for off, idx in enumerate(picked):
        rows[idx]["unix_timestamp"] = str(start + off)
        rows[idx]["_label"] = "1"
        occupied.add(start + off)

def assign_command_anomaly(rows, picked, rng) -> None:
    """Replace the telecommand for every row in the burst with an unusual one."""
    cmd = rng.choice(ANOMALY_COMMANDS)
    for idx in picked:
        rows[idx]["_label"] = "1"
        rows[idx]["telecommand"] = cmd

# ── Injection + CSV writing ─────────────────────────────────────────────────

def inject_write(
    rows: list[dict[str, str]], out_path: Path, fraction: float,
    seed: int | None, elev: float, burst_min: int, burst_max: int,
) -> tuple[int, int]:
    """Main injection routine: label rows, place bursts, deduplicate, write CSV."""
    n = len(rows)
    if n == 0:
        raise ValueError("no rows to inject")

    # All rows must share one satellite / ground station.
    norad = {int(r["norad_id"]) for r in rows}
    lat = {float(r["ground_station_lat"]) for r in rows}
    lon = {float(r["ground_station_lon"]) for r in rows}
    if len(norad) != 1 or len(lat) != 1 or len(lon) != 1:
        raise ValueError("subset must have single norad/lat/lon")

    unix_times = [int(r["unix_timestamp"]) for r in rows]
    t0 = datetime.fromtimestamp(min(unix_times), tz=timezone.utc)
    t1 = datetime.fromtimestamp(max(unix_times), tz=timezone.utc)

    # Figure out where the satellite is NOT visible so anomalies go there.
    passes = merged_pass_intervals(next(iter(norad)), next(iter(lat)),
                                   next(iter(lon)), elev, t0, t1)
    if not passes:
        raise ValueError("no full passes in window; cannot place anomalies")
    gap_edges = edge_windows(gap_intervals(min(unix_times), max(unix_times), passes), burst_max)
    rare_hrs = rare_utc_hours(unix_times)

    rng = random.Random(seed)
    anom_count = min(n, max(burst_min, int(n * fraction))) if fraction > 0 else 0
    sizes = plan_bursts(rng, anom_count, burst_min, burst_max)
    occupied = set(unix_times)

    # Start with every row labeled normal.
    for r in rows:
        r["_label"] = "0"
        r.setdefault("telecommand", NORMAL_COMMAND)

    # Place each burst: always shift in time, sometimes also swap the command.
    used: set[int] = set()
    for sz in sizes:
        free = [i for i in range(n) if i not in used]
        sz = min(sz, len(free))
        if sz == 0:
            break
        picked = rng.sample(free, sz)
        used.update(picked)
        assign_time_anomaly(rows, picked, gap_edges, occupied, rare_hrs, rng)
        if rng.choices(("time", "mixed"), weights=(0.45, 0.55))[0] == "mixed":
            assign_command_anomaly(rows, picked, rng)

    # Sort by timestamp and bump duplicates so every second is unique.
    rows.sort(key=lambda r: int(r["unix_timestamp"]))
    seen: set[int] = set()
    for r in rows:
        t = int(r["unix_timestamp"])
        while t in seen:
            t += 1
        seen.add(t)
        r["unix_timestamp"] = str(t)

    # Write the final CSV with only the ML-relevant columns.
    out_path.parent.mkdir(parents=True, exist_ok=True)
    anomalies = 0
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(OUTPUT_COLS)
        for r in rows:
            if r["_label"] == "1":
                anomalies += 1
            w.writerow([r["unix_timestamp"], r["telecommand"], r["pass_event"], r["_label"]])
    return n, anomalies

# ── CLI entry point ──────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Build sample/year anomaly CSVs for Isolation Forest")
    ap.add_argument("--ground-truth", type=Path, default=None, help="existing base CSV; skip dataset_telecommands")
    ap.add_argument("--no-mongo", action="store_true", help="pass to dataset_telecommands when building the base CSV")
    ap.add_argument("--days", type=int, default=365, help="UTC lookback when building the base CSV")
    ap.add_argument("--sample-rows", type=int, default=100, help="rows in the small anomaly CSV")
    ap.add_argument("--anomaly-fraction", type=float, default=0.05, help="fraction in [0.02, 0.05]")
    ap.add_argument("--seed", type=int, default=42, help="RNG seed for reproducible anomaly placement")
    ap.add_argument("--elev", type=float, default=1140.0, help="observer HAE m; must match dataset_telecommands")
    ap.add_argument("--burst-min", type=int, default=5, help="min rows in one anomaly burst")
    ap.add_argument("--burst-max", type=int, default=10, help="max rows in one anomaly burst")
    ap.add_argument("--out-sample", type=Path,
                    default=Path("evaluation/outputs/anomalies/telecommands_sample_100_anomalies.csv"))
    ap.add_argument("--out-year", type=Path,
                    default=Path("evaluation/outputs/anomalies/telecommands_year_anomalies.csv"))
    args = ap.parse_args()

    if not 0.02 <= args.anomaly_fraction <= 0.05:
        print("--anomaly-fraction must be between 0.02 and 0.05", file=sys.stderr)
        return 1
    if args.burst_min < 1 or args.burst_max < args.burst_min:
        print("--burst-min / --burst-max invalid", file=sys.stderr)
        return 1

    root = repo_root()
    temp_csv: str | None = None
    base_csv = args.ground_truth

    try:
        # If no pre-built CSV was given, generate one from scratch.
        if base_csv is None:
            fd, temp_csv = tempfile.mkstemp(prefix="gt_year_", suffix=".csv")
            os.close(fd)
            base_csv = Path(temp_csv)
            print("Building base telecommand CSV …")
            run_ground_truth_script(root, base_csv, args.days, args.no_mongo)

        full_rows = load_rows(base_csv)
        print(f"Injecting anomalies (fraction={args.anomaly_fraction}, "
              f"burst {args.burst_min}-{args.burst_max}) …")

        # Small sample CSV (quick sanity checks) and full year CSV (real evaluation).
        for label, row_data, out, seed_off in [
            ("sample", [dict(r) for r in full_rows[:min(args.sample_rows, len(full_rows))]],
             args.out_sample, 1),
            ("year", [dict(r) for r in full_rows], args.out_year, 0),
        ]:
            total, anom = inject_write(
                row_data, out, args.anomaly_fraction,
                args.seed + seed_off, args.elev, args.burst_min, args.burst_max)
            print(f"  {label:6s}: {total} rows, is_anomaly=1 -> {anom}  -> {out.resolve()}")
    except (subprocess.CalledProcessError, ValueError, OSError) as err:
        print(err, file=sys.stderr)
        return 1
    finally:
        if temp_csv and os.path.isfile(temp_csv):
            os.unlink(temp_csv)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

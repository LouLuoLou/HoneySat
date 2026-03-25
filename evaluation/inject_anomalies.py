#!/usr/bin/env python3
"""
Build ground truth (via dataset_telecommands.py), then write TWO CSVs for ML training:

  1) telecommands_sample_100_anomalies.csv — first --sample-rows rows (default 100),
     with ~2–5% of rows perturbed + is_anomaly label.
  2) telecommands_year_anomalies.csv — full --days window (default 365), same fraction.

Anomaly: timestamps outside visible passes (10° mask). Bursts: anomalies come in runs of
--burst-min to --burst-max consecutive seconds (same idea as “one then 5–10 right after”).

SETUP
  cd ~/ndss-artifact-eval
  source bin/activate
  pip install -r evaluation/requirements.txt

RUN
  python3 evaluation/inject_anomalies.py --no-mongo

RUN (reuse existing year ground-truth CSV)
  python3 evaluation/inject_anomalies.py --ground-truth telecommands_dataset.csv

Outputs default to CURRENT WORKING DIRECTORY. Override: --out-sample / --out-year
"""
from __future__ import annotations

import argparse
import csv
import os
import random
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import requests
from skyfield.api import EarthSatellite, load, wgs84

COLS = (
    "unix_timestamp",
    "telecommand",
    "norad_id",
    "ground_station_lat",
    "ground_station_lon",
    "pass_event",
)


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def run_ground_truth_script(root: Path, out_csv: Path, days: int, no_mongo: bool) -> None:
    cmd = [
        sys.executable,
        str(root / "evaluation" / "dataset_telecommands.py"),
        "-o",
        str(out_csv),
        "--days",
        str(days),
    ]
    if no_mongo:
        cmd.append("--no-mongo")
    subprocess.run(cmd, cwd=root, check=True)


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        if r.fieldnames is None:
            raise ValueError("empty CSV")
        names = [x.strip() for x in r.fieldnames]
        if names != list(COLS):
            raise ValueError(f"expected columns {list(COLS)}, got {names}")
        return [dict(row) for row in r]


def _to_unix(t) -> int:
    d = t.utc_datetime()
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return int(d.timestamp())


def merged_pass_intervals(
    norad: int, lat: float, lon: float, elev_m: float, start: datetime, end: datetime
) -> list[tuple[int, int]]:
    resp = requests.get(
        f"https://celestrak.org/NORAD/elements/gp.php?CATNR={norad}&FORMAT=TLE",
        timeout=45,
    )
    resp.raise_for_status()
    lines = [x.strip() for x in resp.text.strip().splitlines() if x.strip()]
    if len(lines) < 3:
        raise ValueError(f"No TLE for NORAD {norad}")
    name, l1, l2 = lines[0], lines[1], lines[2]
    ts = load.timescale()
    sat = EarthSatellite(l1, l2, name, ts)
    obs = wgs84.latlon(lat, lon, elevation_m=elev_m)
    times, events = sat.find_events(obs, ts.from_datetime(start), ts.from_datetime(end), altitude_degrees=10.0)
    evs = [int(e) for e in events]
    raw: list[tuple[int, int]] = []
    i = 0
    while i + 2 < len(evs):
        if evs[i] == 0 and evs[i + 1] == 1 and evs[i + 2] == 2:
            raw.append((_to_unix(times[i]), _to_unix(times[i + 2])))
            i += 3
        else:
            i += 1
    if not raw:
        return []
    raw.sort()
    out = [raw[0]]
    for lo, hi in raw[1:]:
        plo, phi = out[-1]
        if lo <= phi + 1:
            out[-1] = (plo, max(phi, hi))
        else:
            out.append((lo, hi))
    return out


def gaps(t_lo: int, t_hi: int, merged: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if t_lo > t_hi:
        return []
    if not merged:
        return [(t_lo, t_hi)]
    g, cur = [], t_lo
    for lo, hi in merged:
        a, b = max(lo, t_lo), min(hi, t_hi)
        if cur < a:
            g.append((cur, a - 1))
        cur = max(cur, b + 1)
    if cur <= t_hi:
        g.append((cur, t_hi))
    return [(x, y) for x, y in g if x <= y]


def pick_outside(rng: random.Random, t_lo: int, t_hi: int, merged: list[tuple[int, int]]) -> int:
    g = gaps(t_lo, t_hi, merged)
    if not g:
        raise ValueError("no time outside passes inside this CSV window")
    w = [b - a + 1 for a, b in g]
    pick, acc = rng.randrange(sum(w)), 0
    for (a, b), wt in zip(g, w):
        acc += wt
        if pick < acc:
            return a + (pick - (acc - wt))
    return g[-1][1]


def outside(u: int, merged: list[tuple[int, int]]) -> bool:
    return not any(lo <= u <= hi for lo, hi in merged)


def plan_bursts(rng: random.Random, k: int, bmin: int, bmax: int) -> list[int]:
    """Split k rows into burst lengths; each piece in [bmin, bmax] when possible."""
    out, left = [], k
    while left > 0:
        if left < bmin:
            out.append(left)
            break
        sz = min(left, rng.randint(bmin, bmax))
        out.append(sz)
        left -= sz
    return out


def pick_burst_start_fast(
    rng: random.Random,
    glist: list[tuple[int, int]],
    L: int,
    occupied: set[int],
    tries_per_gap: int = 80,
) -> int | None:
    """
    Find t0 so t0..t0+L-1 lies in one gap and avoids occupied. O(tries) per call, no huge lists.
    """
    wide = [(a, b) for a, b in glist if b - a + 1 >= L]
    if not wide:
        return None
    rng.shuffle(wide)
    for a, b in wide:
        hi_start = b - L + 1
        for _ in range(tries_per_gap):
            t0 = rng.randint(a, hi_start)
            if all((t0 + i) not in occupied for i in range(L)):
                return t0
    return None


def inject_write(
    rows: list[dict[str, str]],
    out_path: Path,
    frac: float,
    seed: int | None,
    elev: float,
    burst_min: int,
    burst_max: int,
) -> tuple[int, int]:
    n = len(rows)
    if n == 0:
        raise ValueError("no rows to inject")

    norads = {int(r["norad_id"]) for r in rows}
    lats = {float(r["ground_station_lat"]) for r in rows}
    lons = {float(r["ground_station_lon"]) for r in rows}
    if len(norads) != 1 or len(lats) != 1 or len(lons) != 1:
        raise ValueError("subset must have single norad/lat/lon")
    norad = next(iter(norads))
    lat, lon = next(iter(lats)), next(iter(lons))

    ts = [int(r["unix_timestamp"]) for r in rows]
    t_lo, t_hi = min(ts), max(ts)
    start = datetime.fromtimestamp(t_lo, tz=timezone.utc)
    end = datetime.fromtimestamp(t_hi, tz=timezone.utc)

    merged = merged_pass_intervals(norad, lat, lon, elev, start, end)
    if not merged:
        raise ValueError("no full passes in window; cannot place out-of-pass times")
    pick_outside(random.Random(0), t_lo, t_hi, merged)

    glist = gaps(t_lo, t_hi, merged)
    rng = random.Random(seed)
    k = (max(1, int(n * frac)) if frac > 0 else 0) if n else 0
    k = min(n, k)
    burst_sizes = plan_bursts(rng, k, burst_min, burst_max)

    occupied = set(ts)
    chosen: list[int] = []

    for want in burst_sizes:
        L = want
        t0 = None
        while L >= 1:
            t0 = pick_burst_start_fast(rng, glist, L, occupied)
            if t0 is not None:
                break
            L -= 1
        if t0 is None:
            raise ValueError("could not place burst; lower --burst-max or fraction")

        pool = [i for i in range(n) if i not in chosen]
        if len(pool) < L:
            raise ValueError("not enough rows for burst")
        pick = rng.sample(pool, L)
        for j, idx in enumerate(pick):
            u = t0 + j
            rows[idx]["unix_timestamp"] = str(u)
            rows[idx]["_t"] = "1"
            occupied.add(u)
        chosen.extend(pick)

    for r in rows:
        r.setdefault("_t", "0")

    rows.sort(key=lambda r: int(r["unix_timestamp"]))
    seen: set[int] = set()
    for r in rows:
        u = int(r["unix_timestamp"])
        while u in seen:
            u += 1
        seen.add(u)
        r["unix_timestamp"] = str(u)

    out_rows: list[list[str]] = []
    n1 = 0
    for r in rows:
        u = int(r["unix_timestamp"])
        lab = "1" if r["_t"] == "1" and outside(u, merged) else "0"
        if lab == "1":
            n1 += 1
        out_rows.append([r[c] for c in COLS] + [lab])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(list(COLS) + ["is_anomaly"])
        w.writerows(out_rows)

    return n, n1


def main() -> int:
    ap = argparse.ArgumentParser(description="Build GT + two burst-anomaly CSVs (sample + year)")
    ap.add_argument("--ground-truth", type=Path, default=None, help="existing year CSV; skip dataset_telecommands")
    ap.add_argument("--no-mongo", action="store_true", help="pass to dataset_telecommands when building GT")
    ap.add_argument("--days", type=int, default=365, help="UTC lookback for GT when building")
    ap.add_argument("--sample-rows", type=int, default=100, help="rows in small output (head of sorted GT)")
    ap.add_argument(
        "--anomaly-fraction",
        type=float,
        default=0.05,
        help="fraction in [0.02, 0.05] of rows to perturb in EACH output file",
    )
    ap.add_argument("--seed", type=int, default=42, help="RNG seed for year file; sample uses seed+1")
    ap.add_argument("--elev", type=float, default=1140.0, help="observer HAE m; must match dataset_telecommands")
    ap.add_argument("--burst-min", type=int, default=5, help="min consecutive seconds per burst")
    ap.add_argument("--burst-max", type=int, default=10, help="max consecutive seconds per burst")
    ap.add_argument("--out-sample", type=Path, default=Path("telecommands_sample_100_anomalies.csv"))
    ap.add_argument("--out-year", type=Path, default=Path("telecommands_year_anomalies.csv"))
    args = ap.parse_args()

    if not 0.02 <= args.anomaly_fraction <= 0.05:
        print("--anomaly-fraction must be between 0.02 and 0.05", file=sys.stderr)
        return 1
    if args.burst_min < 1 or args.burst_max < args.burst_min:
        print("--burst-min / --burst-max invalid", file=sys.stderr)
        return 1

    root = repo_root()
    tmp: str | None = None
    gt_path = args.ground_truth

    try:
        if gt_path is None:
            fd, tmp = tempfile.mkstemp(prefix="gt_year_", suffix=".csv")
            os.close(fd)
            gt_path = Path(tmp)
            print("Building ground truth (dataset_telecommands.py) …")
            run_ground_truth_script(root, gt_path, args.days, args.no_mongo)

        full = load_rows(gt_path)
        sample = [dict(r) for r in full[: max(0, min(args.sample_rows, len(full)))]]

        print(
            f"Injecting burst anomalies (fraction={args.anomaly_fraction}, "
            f"burst {args.burst_min}-{args.burst_max}s) …"
        )
        ny, y1 = inject_write(
            sample,
            args.out_sample,
            args.anomaly_fraction,
            args.seed + 1,
            args.elev,
            args.burst_min,
            args.burst_max,
        )
        print(f"  sample: {ny} rows, is_anomaly=1 -> {y1}  -> {args.out_sample.resolve()}")

        ny, y1 = inject_write(
            [dict(r) for r in full],
            args.out_year,
            args.anomaly_fraction,
            args.seed,
            args.elev,
            args.burst_min,
            args.burst_max,
        )
        print(f"  year:   {ny} rows, is_anomaly=1 -> {y1}  -> {args.out_year.resolve()}")
    except (subprocess.CalledProcessError, ValueError, OSError) as e:
        print(e, file=sys.stderr)
        return 1
    finally:
        if tmp and os.path.isfile(tmp):
            os.unlink(tmp)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

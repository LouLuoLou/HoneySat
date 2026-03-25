#!/usr/bin/env python3
"""
Replace some CSV rows' unix times with times outside satellite passes (10° mask, same as dataset_telecommands).
Optional --add-label writes is_anomaly from the final timestamps after sort/dedupe.
"""
from __future__ import annotations

import argparse
import csv
import random
import sys
from datetime import datetime, timezone

import requests
from skyfield.api import EarthSatellite, load, wgs84

# Ground-truth CSV from dataset_telecommands.py must use exactly this header order.
EXPECTED_COLS = (
    "unix_timestamp",
    "telecommand",
    "norad_id",
    "ground_station_lat",
    "ground_station_lon",
    "pass_event",
)


def sky_time_to_unix(t) -> int:
    """Skyfield time object -> UTC unix seconds (int)."""
    d = t.utc_datetime()
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return int(d.timestamp())


def fetch_pass_intervals_unix(
    norad: int,
    lat: float,
    lon: float,
    elev_m: float,
    start: datetime,
    end: datetime,
) -> list[tuple[int, int]]:
    """
    Recompute pass visibility from scratch (must match how ground truth was built).

    Returns merged intervals [rise_unix, set_unix] for each pass where the satellite is
    above 10°; rise/peak/set come from Skyfield's find_events (0, 1, 2).
    """
    r = requests.get(
        f"https://celestrak.org/NORAD/elements/gp.php?CATNR={norad}&FORMAT=TLE",
        timeout=45,
    )
    r.raise_for_status()
    L = [x.strip() for x in r.text.strip().splitlines() if x.strip()]
    if len(L) < 3:
        raise ValueError(f"No TLE for NORAD {norad}")
    name, l1, l2 = L[0], L[1], L[2]
    ts = load.timescale()
    sat = EarthSatellite(l1, l2, name, ts)
    obs = wgs84.latlon(lat, lon, elevation_m=elev_m)
    # Same mask as dataset_telecommands: above 10° elevation between start and end (CSV time span).
    times, events = sat.find_events(obs, ts.from_datetime(start), ts.from_datetime(end), altitude_degrees=10.0)
    intervals: list[tuple[int, int]] = []
    evs = [int(e) for e in events]
    i = 0
    while i + 2 < len(evs):
        # Only full pass: rise (0) -> culmination (1) -> set (2). Skip partial sequences at window edges.
        if evs[i] == 0 and evs[i + 1] == 1 and evs[i + 2] == 2:
            intervals.append((sky_time_to_unix(times[i]), sky_time_to_unix(times[i + 2])))
            i += 3
        else:
            i += 1
    return merge_intervals(intervals)


def merge_intervals(ivs: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Sort and merge overlapping or back-to-back passes so 'outside pass' gaps are correct."""
    if not ivs:
        return []
    ivs = sorted(ivs)
    out = [ivs[0]]
    for lo, hi in ivs[1:]:
        plo, phi = out[-1]
        # +1: treat adjacent seconds as one continuous visible span
        if lo <= phi + 1:
            out[-1] = (plo, max(phi, hi))
        else:
            out.append((lo, hi))
    return out


def gaps_in_range(t_min: int, t_max: int, merged: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """
    Within [t_min, t_max] (the CSV's unix span), list maximal sub-ranges with no pass coverage.

    Those gaps are where we may place 'anomalous' timestamps: still in the dataset window,
    but not during any pass [rise, set].
    """
    if t_min > t_max:
        return []
    if not merged:
        return [(t_min, t_max)]
    gaps: list[tuple[int, int]] = []
    cur = t_min
    for lo, hi in merged:
        lo_c = max(lo, t_min)
        hi_c = min(hi, t_max)
        if cur < lo_c:
            gaps.append((cur, lo_c - 1))
        cur = max(cur, hi_c + 1)
    if cur <= t_max:
        gaps.append((cur, t_max))
    return [(a, b) for a, b in gaps if a <= b]


def random_ts_outside_passes(rng: random.Random, t_min: int, t_max: int, merged: list[tuple[int, int]]) -> int:
    """Pick one unix second uniformly from the union of all gap intervals (each second equally likely)."""
    gaps = gaps_in_range(t_min, t_max, merged)
    if not gaps:
        raise ValueError(
            "No time outside pass intervals inside CSV window (passes may cover the whole span)."
        )
    weights = [b - a + 1 for a, b in gaps]  # length of each gap in seconds
    total = sum(weights)
    pick = rng.randrange(total)
    acc = 0
    for (a, b), w in zip(gaps, weights):
        acc += w
        if pick < acc:
            return a + (pick - (acc - w))
    return gaps[-1][1]


def outside_passes(u: int, merged: list[tuple[int, int]]) -> bool:
    """True iff unix second u is not inside any merged pass interval."""
    for lo, hi in merged:
        if lo <= u <= hi:
            return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="Inject out-of-pass timestamps into ground-truth CSV")
    ap.add_argument("-i", "--input", required=True, help="ground truth CSV from dataset_telecommands.py")
    ap.add_argument("-o", "--output", required=True, help="output CSV path")
    ap.add_argument(
        "--anomaly-fraction",
        type=float,
        default=0.05,
        help="fraction in [0.02, 0.05] of rows to perturb (default 0.05)",
    )
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--norad", type=int, default=None)
    ap.add_argument("--lat", type=float, default=None)
    ap.add_argument("--lon", type=float, default=None)
    ap.add_argument("--elev", type=float, default=1140.0, help="observer HAE m (not in CSV)")
    ap.add_argument(
        "--add-label",
        action="store_true",
        help="append is_anomaly: 1 only if timestamp lies outside all pass intervals after dedupe",
    )
    args = ap.parse_args()

    if not 0.02 <= args.anomaly_fraction <= 0.05:
        print("--anomaly-fraction must be between 0.02 and 0.05", file=sys.stderr)
        return 1

    # --- Load and validate CSV shape ---
    with open(args.input, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            print("Empty CSV", file=sys.stderr)
            return 1
        names = [x.strip() for x in reader.fieldnames]
        if names != list(EXPECTED_COLS):
            print(f"Expected columns {list(EXPECTED_COLS)}, got {names}", file=sys.stderr)
            return 1
        rows = [dict(r) for r in reader]

    n = len(rows)
    if n == 0:
        print("No data rows", file=sys.stderr)
        return 1

    # --- Site / satellite identity: CLI overrides, else exactly one value must appear in the file ---
    norads = {int(r["norad_id"]) for r in rows}
    lats = {float(r["ground_station_lat"]) for r in rows}
    lons = {float(r["ground_station_lon"]) for r in rows}
    if args.norad is not None:
        norad = args.norad
    elif len(norads) == 1:
        norad = next(iter(norads))
    else:
        print(f"Multiple norad_id values {norads}; pass --norad", file=sys.stderr)
        return 1
    if args.lat is not None:
        lat = args.lat
    elif len(lats) == 1:
        lat = next(iter(lats))
    else:
        print(f"Multiple lat values {lats}; pass --lat", file=sys.stderr)
        return 1
    if args.lon is not None:
        lon = args.lon
    elif len(lons) == 1:
        lon = next(iter(lons))
    else:
        print(f"Multiple lon values {lons}; pass --lon", file=sys.stderr)
        return 1

    # Pass geometry is derived from [min_ts, max_ts] in the file, not "now".
    ts_vals = [int(r["unix_timestamp"]) for r in rows]
    t_min, t_max = min(ts_vals), max(ts_vals)
    start = datetime.fromtimestamp(t_min, tz=timezone.utc)
    end = datetime.fromtimestamp(t_max, tz=timezone.utc)

    try:
        merged = fetch_pass_intervals_unix(norad, lat, lon, args.elev, start, end)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1
    if not merged:
        print(
            "No full rise peak set passes in CSV window; cannot define out-of-pass times.",
            file=sys.stderr,
        )
        return 1

    # Fail fast if there is no "gap" left (e.g. passes tile the whole span). Uses fixed RNG; not user seed.
    try:
        random_ts_outside_passes(random.Random(0), t_min, t_max, merged)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1

    # --- How many rows to perturb: floor(n * fraction), at least 1 if fraction > 0, never more than n ---
    rng = random.Random(args.seed)
    k = int(n * args.anomaly_fraction)
    if args.anomaly_fraction > 0 and k < 1:
        k = 1
    k = min(k, n)

    inject_idx = set(rng.sample(range(n), k)) if k else set()
    for i in inject_idx:
        rows[i]["unix_timestamp"] = str(random_ts_outside_passes(rng, t_min, t_max, merged))
        rows[i]["_targeted"] = "1"  # marked for labeling; not written to CSV
    for r in rows:
        if "_targeted" not in r:
            r["_targeted"] = "0"

    # --- Same uniqueness rule as dataset_telecommands: sort by time, bump +1 on duplicate seconds ---
    rows.sort(key=lambda r: int(r["unix_timestamp"]))
    seen: set[int] = set()
    for r in rows:
        u = int(r["unix_timestamp"])
        while u in seen:
            u += 1
        seen.add(u)
        r["unix_timestamp"] = str(u)

    # --- Build output rows; is_anomaly uses FINAL timestamp after dedupe ---
    out: list[list[str]] = []
    for r in rows:
        row = [r[c] for c in EXPECTED_COLS]
        if args.add_label:
            u = int(r["unix_timestamp"])
            if r["_targeted"] == "1":
                # Injected row: label 1 only if dedupe did not push it back inside a pass
                lab = "1" if outside_passes(u, merged) else "0"
            else:
                lab = "0"
            row.append(lab)
        out.append(row)

    hdr = list(EXPECTED_COLS)
    if args.add_label:
        hdr.append("is_anomaly")

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(hdr)
        w.writerows(out)

    n_lab = sum(1 for r in out if args.add_label and r[-1] == "1")
    print(f"rows={n}  targeted={len(inject_idx)}  is_anomaly=1 count={n_lab if args.add_label else 'n/a'}  -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
Merge NORAD-based pass times (CelesTrak + Skyfield) and optional Mongo com_ping rows into one CSV.
Run from repo root: pip install -r evaluation/requirements.txt then
python3 evaluation/extrapolate_telecommands_dataset.py -o out.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import requests
from skyfield.api import EarthSatellite, load, wgs84

CMD = "1: com_ping 10"
# find_events returns 0,1,2; we label them rise, peak (culmination), set
EV = ("rise", "peak", "set")


def main() -> int:
    # All knobs: output path, NORAD and ground site, window length, Mongo host, dry-run / skip DB
    p = argparse.ArgumentParser(description="NORAD passes + optional Mongo com_ping -> CSV")
    p.add_argument("-o", "--output", default="telecommands_dataset.csv")
    p.add_argument("--norad", type=int, default=62171, help="CelesTrak catalog id (NORAD)")
    p.add_argument("--lat", type=float, default=31.7619)
    p.add_argument("--lon", type=float, default=-106.4850)
    p.add_argument("--elev", type=float, default=1140.0, help="observer HAE above WGS84, m")
    p.add_argument("--days", type=int, default=365, help="UTC window length ending at now")
    p.add_argument("--host", default=os.environ.get("MONGO_HOST", "localhost"))
    p.add_argument("--port", type=int, default=int(os.environ.get("MONGO_PORT", "27017")))
    p.add_argument("--no-mongo", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=a.days)

    # Passes: NORAD goes in the CelesTrak URL only. Skyfield loads the TLE, places an observer at
    # lat/lon/elev, and finds rise/peak/set whenever the satellite is above 10 deg elevation.
    r = requests.get(
        f"https://celestrak.org/NORAD/elements/gp.php?CATNR={a.norad}&FORMAT=TLE", timeout=45
    )
    r.raise_for_status()
    L = [x.strip() for x in r.text.strip().splitlines() if x.strip()]
    if len(L) < 3:
        print(f"No TLE for NORAD {a.norad}", file=sys.stderr)
        return 1
    name, l1, l2 = L[0], L[1], L[2]
    ts = load.timescale()
    # Skyfield wants (tle_line1, tle_line2, name, timescale) — easy to mix up order
    sat = EarthSatellite(l1, l2, name, ts)
    obs = wgs84.latlon(a.lat, a.lon, elevation_m=a.elev)
    times, events = sat.find_events(obs, ts.from_datetime(start), ts.from_datetime(end), altitude_degrees=10.0)

    rows: list[tuple] = []
    for ti, ev in zip(times, events):
        d = ti.utc_datetime()
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        rows.append((int(d.timestamp()), CMD, a.norad, a.lat, a.lon, EV[int(ev)]))

    # Mongo: same root user URI as dump_mongodb.py. Collection name spelling matches the real DB.
    # pymongo imported inside so --no-mongo still works if the package is missing.
    if not a.no_mongo:
        try:
            from pymongo import MongoClient
            from pymongo.errors import ConnectionFailure, OperationFailure
        except ImportError:
            print("pip install pymongo or use --no-mongo", file=sys.stderr)
            return 1
        uri = (
            f"mongodb://honeysat_root_1:honeysat_rootpass_1234@{a.host}:{a.port}/honeysat_log?authSource=admin"
        )
        try:
            cli = MongoClient(uri, serverSelectionTimeoutMS=8000)
            cli.admin.command("ping")
            for doc in cli["honeysat_log"]["TelnetMessageRecieved"].find({}):
                raw = doc.get("time")
                if not isinstance(raw, datetime):
                    continue
                t = raw.replace(tzinfo=timezone.utc) if raw.tzinfo is None else raw.astimezone(timezone.utc)
                if not (start <= t <= end):
                    continue
                data = doc.get("data")
                if isinstance(data, str):
                    try:
                        data = json.loads(data)
                    except (json.JSONDecodeError, TypeError):
                        continue
                if not isinstance(data, dict):
                    continue
                msg = data.get("message")
                if not isinstance(msg, str) or "com_ping" not in msg:
                    continue
                rows.append((int(t.timestamp()), CMD, a.norad, a.lat, a.lon, "mongo"))
        except ConnectionFailure as e:
            print(f"Mongo unreachable: {e}  (try --no-mongo)", file=sys.stderr)
            return 1
        except OperationFailure as e:
            print(f"Mongo auth: {e}", file=sys.stderr)
            return 1

    # Merge: sort by time. Pass and mongo rows can share the same unix second; bump +1 until unique.
    rows.sort(key=lambda x: x[0])
    seen, out = set(), []
    for row in rows:
        u, rest = row[0], row[1:]
        while u in seen:
            u += 1
        seen.add(u)
        out.append((u,) + rest)

    nm = sum(1 for x in out if x[5] == "mongo")
    print(f"{start.isoformat()} .. {end.isoformat()}  norad={a.norad}  passes={len(out) - nm}  mongo={nm}  total={len(out)}")
    if a.dry_run:
        return 0

    hdr = ["unix_timestamp", "telecommand", "norad_id", "ground_station_lat", "ground_station_lon", "pass_event"]
    with open(a.output, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(hdr)
        w.writerows(out)
    print("Wrote", a.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

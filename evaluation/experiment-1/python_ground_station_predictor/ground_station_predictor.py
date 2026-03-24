#!/usr/bin/env python3
"""
ground_station_predictor.py

Given a NORAD catalog number (via input.env) or raw TLE piped on stdin, fetch the latest TLE,
propagate the satellite using Skyfield and report the point on Earth
(lat, lon, alt) directly under the satellite X minutes in the future.

This can be used to estimate where you'd want a "virtual ground station" to be
to see the satellite at that time (i.e. the subsatellite point).

Dependencies:
    pip install skyfield

Usage (option 1: create input.env with SATELLITE_NORAD and just run the script):
    python3 ground_station_predictor.py

Usage (option 2: pass a TLE on stdin):
    python3 ground_station_predictor.py << 'EOF'
    ISS (ZARYA)
    1 25544U 98067A   25301.50000000  .00021000  00000-0  39400-3 0  9993
    2 25544  51.6420  90.1234 0003500  75.0000  20.0000 15.50000000 12345
    EOF

Extendability:
- You can import `get_future_subpoint()` in other modules,
  or change `FUTURE_MINUTES` to scan multiple times in the future.

Outputs:
- honeysat-api.env and honeysat-webpage-v2.env will be (re)generated with
  GROUND_STATION_LAT / GROUND_STATION_LON for docker compose consumption.
"""

from __future__ import annotations

import argparse
from datetime import timezone
from pathlib import Path
from dataclasses import dataclass
from typing import List, Tuple

import requests
from skyfield.api import EarthSatellite, load, wgs84


# === Configuration ============================================================
FUTURE_MINUTES = 8  # how far ahead to project, in minutes
ROOT_DIR = Path(__file__).resolve().parent.parent
INPUT_ENV_PATH = ROOT_DIR / "input.env"
HONEY_SAT_API_ENV_PATH = ROOT_DIR / "honeysat-api.env"
WEBPAGE_ENV_PATH = ROOT_DIR / "honeysat-webpage-v2.env"
TLE_SOURCE_URL = "https://celestrak.org/NORAD/elements/gp.php"
SATELLITE_NORAD_KEY = "SATELLITE_NORAD"
GROUND_STATION_TARGETS: Tuple[Path, Path] = (
    HONEY_SAT_API_ENV_PATH,
    WEBPAGE_ENV_PATH,
)


# === Data structures =========================================================
@dataclass
class SubpointResult:
    """Container for the subsatellite point info."""
    future_minutes: int
    when_utc_iso: str
    satellite_name: str
    norad_catalog_number: str
    latitude_deg: float
    longitude_deg: float
    altitude_km: float


# === TLE helpers =============================================================
def _read_env_file(path: Path) -> dict:
    """
    Parse a simple KEY=VALUE env file into a dict.
    Ignores blank lines and comments that start with '#'.
    """
    if not path.exists():
        raise FileNotFoundError(f"Required env file not found: {path}")
    env: dict[str, str] = {}
    for raw_line in path.read_text(encoding="ascii").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip()
    return env


def _fetch_tle_for_norad(norad_number: str) -> List[str]:
    """
    Download TLE data for a given NORAD catalog number.
    """
    response = requests.get(
        TLE_SOURCE_URL,
        params={"CATNR": norad_number, "FORMAT": "TLE"},
        timeout=15,
    )
    response.raise_for_status()
    lines = [line.strip() for line in response.text.splitlines() if line.strip()]
    if len(lines) < 2:
        raise ValueError(f"Could not retrieve TLE for NORAD {norad_number}")

    # Some feeds return three-line sets (name + 2 lines), some only two.
    if len(lines) == 2:
        return ["SATELLITE", lines[0], lines[1]]
    return lines[:3]


def _extract_norad_from_line1(line1: str) -> str:
    """
    Extract the NORAD catalog number from TLE line 1.
    """
    if len(line1) < 7:
        raise ValueError("TLE line 1 is unexpectedly short.")
    norad_digits = line1[2:7].strip()
    if not norad_digits.isdigit():
        raise ValueError(f"Unable to parse NORAD number from TLE line 1: {line1}")
    return norad_digits


def _write_ground_station_env(path: Path, latitude: float, longitude: float) -> None:
    """
    Persist ground station coordinates for docker compose consumption.
    """
    content = (
        f"GROUND_STATION_LAT={latitude:.6f}\n"
        f"GROUND_STATION_LON={longitude:.6f}\n"
    )
    path.write_text(content, encoding="ascii")


# === Core logic ==============================================================
def _normalize_tle_lines(tle_lines: List[str]) -> Tuple[str, str, str]:
    """
    Accepts 2-line or 3-line TLE input and returns (name, line1, line2).

    Rules:
    - If there are exactly 2 lines, we synthesize a name "SATELLITE".
    - If there are 3+ lines, we assume first is a name, next two are line1/line2.
    - Empty lines are ignored.
    """
    cleaned = [ln.strip() for ln in tle_lines if ln.strip()]
    if len(cleaned) < 2:
        raise ValueError("TLE must contain at least 2 non-empty lines.")
    if len(cleaned) == 2:
        name = "SATELLITE"
        l1, l2 = cleaned
    else:
        name, l1, l2 = cleaned[0], cleaned[1], cleaned[2]

    # Basic sanity: TLE line1 starts with '1 ' and line2 with '2 '
    if not l1.startswith("1 ") or not l2.startswith("2 "):
        raise ValueError("TLE lines don't look valid (expected '1 ' and '2 ' prefixes).")
    return name, l1, l2


def get_future_subpoint(
    tle_lines: List[str],
    minutes_ahead: int = FUTURE_MINUTES,
) -> SubpointResult:
    """
    Given raw TLE lines and a lead time in minutes,
    propagate with Skyfield and return the subsatellite point.

    Steps:
    - Parse TLE
    - Get current UTC time
    - Advance by `minutes_ahead`
    - Compute subpoint (lat/lon/alt above WGS84)
    """
    # Parse the TLE
    name, l1, l2 = _normalize_tle_lines(tle_lines)
    norad_catalog_number = _extract_norad_from_line1(l1)

    # Skyfield time objects
    ts = load.timescale()
    now = ts.now()  # current UTC
    delta_days = minutes_ahead / (24.0 * 60.0)
    future_t = now + delta_days

    # Build satellite model
    sat = EarthSatellite(l1, l2, name, ts)

    # Get Earth-fixed subpoint at future time
    geocentric = sat.at(future_t)
    subpoint = wgs84.subpoint(geocentric)

    # Extract geodetic coordinates
    lat_deg = subpoint.latitude.degrees      # +N, -S
    lon_deg = subpoint.longitude.degrees     # +E, -W (range -180..180)
    alt_km = subpoint.elevation.km           # height of sat above that point

    # Make human-friendly timestamp string
    future_dt = future_t.utc_datetime().replace(tzinfo=timezone.utc)
    future_iso = future_dt.isoformat()

    return SubpointResult(
        future_minutes=minutes_ahead,
        when_utc_iso=future_iso,
        satellite_name=name,
        norad_catalog_number=norad_catalog_number,
        latitude_deg=lat_deg,
        longitude_deg=lon_deg,
        altitude_km=alt_km,
    )


# === Convenience printing =====================================================
def pretty_print_result(result: SubpointResult) -> None:
    """
    Print a nice summary of where the satellite will be directly overhead.
    """
    print("Predicted sub-satellite point")
    print("----------------------------")
    print(f"Satellite:         {result.satellite_name} (NORAD {result.norad_catalog_number})")
    print(f"Time (UTC):        {result.when_utc_iso}")
    print(f"Lead time:         {result.future_minutes} minute(s) ahead")
    # Latitude: N/S, Longitude: E/W helper
    lat_dir = "N" if result.latitude_deg >= 0 else "S"
    lon_dir = "E" if result.longitude_deg >= 0 else "W"
    print(f"Latitude:          {abs(result.latitude_deg):.4f}° {lat_dir}")
    print(f"Longitude:         {abs(result.longitude_deg):.4f}° {lon_dir}")
    print(f"Raw lat, lon (deg): {result.latitude_deg:.6f}, {result.longitude_deg:.6f}")
    print(f"Satellite altitude: {result.altitude_km:.2f} km")


def _read_tle_from_stdin_if_available() -> List[str] | None:
    """
    If the user piped or <<EOF'd a TLE into stdin, read it.
    If stdin is a TTY (user just ran the script normally), return None.
    """
    import sys
    if sys.stdin.isatty():
        return None

    # Read all stdin lines
    data = sys.stdin.read().strip().splitlines()
    # If user actually piped something meaningful, use it
    nonempty = [ln for ln in data if ln.strip()]
    if len(nonempty) >= 2:
        return nonempty
    return None


def _load_tle_lines(norad_override: str | None = None) -> List[str]:
    """
    Determine the TLE to use: prefer stdin, otherwise fetch by NORAD from input.env.
    """
    tle_from_stdin = _read_tle_from_stdin_if_available()
    if tle_from_stdin:
        return tle_from_stdin

    if norad_override:
        return _fetch_tle_for_norad(norad_override)

    env_vars = _read_env_file(INPUT_ENV_PATH)
    norad_number = env_vars.get(SATELLITE_NORAD_KEY)
    if not norad_number:
        raise KeyError(f"{SATELLITE_NORAD_KEY} missing from {INPUT_ENV_PATH}")
    return _fetch_tle_for_norad(norad_number)


def _persist_ground_station_coordinates(latitude: float, longitude: float) -> None:
    """
    Write the derived ground station coordinates to each target env file.
    """
    for target in GROUND_STATION_TARGETS:
        _write_ground_station_env(target, latitude, longitude)
        print(f"Ground station env written to: {target}")


def _parse_args() -> argparse.Namespace:
    """CLI options for ad-hoc overrides."""
    parser = argparse.ArgumentParser(description="Predict future sub-satellite point")
    parser.add_argument(
        "--norad",
        help="NORAD catalog number to fetch when skipping input.env",
    )
    parser.add_argument(
        "--minutes",
        type=int,
        help="Override minutes in the future to project (defaults to FUTURE_MINUTES)",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    minutes_ahead = args.minutes if args.minutes is not None else FUTURE_MINUTES
    tle_lines = _load_tle_lines(args.norad)
    result = get_future_subpoint(tle_lines, minutes_ahead)
    pretty_print_result(result)
    print()
    _persist_ground_station_coordinates(result.latitude_deg, result.longitude_deg)


if __name__ == "__main__":
    main()

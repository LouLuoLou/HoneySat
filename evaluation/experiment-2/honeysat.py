#!/usr/bin/env python3
"""HoneySat pass planner using live TLE and geocoded ground station.

Usage examples
--------------
    python honeysat.py csp "Sentinel-6A" "Canberra, Australia"
    python honeysat.py start csp "Sentinel-6A" "Canberra, Australia"
    python honeysat.py stop csp

The tool keeps no built-in defaults. It takes the desired HoneySat link mode
(`csp` or `ccsds`), the satellite name, and a single ground station location. At
runtime it queries CelesTrak for a matching TLE, geocodes the location via the
Nominatim API, and propagates the orbit with Skyfield to list the next few
visible passes over the requested site.
"""

from __future__ import annotations

import argparse
import subprocess
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Sequence, Tuple

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SITE_PACKAGES_CANDIDATE = PROJECT_ROOT / "lib"
if SITE_PACKAGES_CANDIDATE.exists():
    for entry in SITE_PACKAGES_CANDIDATE.glob("python*/site-packages"):
        if str(entry) not in sys.path:
            sys.path.insert(0, str(entry))


try:  # Third-party dependencies
    import requests
    from skyfield.api import EarthSatellite, load, wgs84
except ImportError as exc:  # pragma: no cover - explicit user feedback path
    missing = "requests" if "requests" in str(exc) else "skyfield"
    raise SystemExit(
        f"Missing dependency '{missing}'. Install requirements with "
        "'python3 -m pip install requests skyfield'."
    )


@dataclass(frozen=True)
class GroundStation:
    identifier: str
    name: str
    location: str
    latitude_deg: float
    longitude_deg: float
    altitude_m: float = 0.0


@dataclass(frozen=True)
class PassWindow:
    start_utc: datetime
    end_utc: datetime
    peak_utc: datetime
    max_elevation_deg: float
    ground_station: GroundStation


CELESTRAK_GP_ENDPOINT = "https://celestrak.org/NORAD/elements/gp.php"
GEOCODING_ENDPOINT = "https://nominatim.openstreetmap.org/search"
GEOCODING_USER_AGENT = "honeysat-cli/1.0"


def geocode_location(query: str) -> Tuple[str, float, float]:
    params = {"format": "jsonv2", "limit": 1, "q": query}
    headers = {"User-Agent": GEOCODING_USER_AGENT}
    try:
        response = requests.get(GEOCODING_ENDPOINT, params=params, headers=headers, timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:  # pragma: no cover - requires network
        raise LookupError(f"Geocoding failed: {exc}") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise LookupError("Geocoding response was not valid JSON") from exc

    if not payload:
        raise LookupError(f"No results for '{query}'.")

    entry = payload[0]
    try:
        latitude = float(entry["lat"])
        longitude = float(entry["lon"])
    except (KeyError, TypeError, ValueError) as exc:
        raise LookupError("Incomplete geocoding result (missing coordinates)") from exc

    label = entry.get("display_name", query)
    return label, latitude, longitude


def _normalize_identifier(seed: str) -> str:
    candidate = re.sub(r"[^a-z0-9]+", "-", seed.lower()).strip("-")
    return candidate or "station"


def _split_gp_response(raw: str):
    entries = []
    buffer: list[str] = []

    def flush(buf: list[str]) -> None:
        if len(buf) == 2 and buf[0].startswith("1 ") and buf[1].startswith("2 "):
            entries.append(("UNKNOWN", buf[0], buf[1]))
        elif len(buf) == 3 and buf[1].startswith("1 ") and buf[2].startswith("2 "):
            name_line = buf[0]
            name = name_line[2:].strip() if name_line.startswith("0 ") else name_line
            entries.append((name, buf[1], buf[2]))

    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            flush(buffer)
            buffer = []
            continue
        buffer.append(stripped)
        if len(buffer) > 3:
            buffer = buffer[-3:]
        if len(buffer) == 3 and buffer[1].startswith("1 ") and buffer[2].startswith("2 "):
            flush(buffer)
            buffer = []

    flush(buffer)
    return entries


def fetch_tle_for_name(query: str) -> Tuple[str, str, str]:
    params = {"FORMAT": "TLE", "NAME": query}
    try:
        response = requests.get(CELESTRAK_GP_ENDPOINT, params=params, timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:  # pragma: no cover - requires network
        raise LookupError(f"Unable to contact CelesTrak: {exc}") from exc

    records = _split_gp_response(response.text)
    if not records:
        raise LookupError(f"No TLE entries found for '{query}'.")

    target = query.strip().lower()
    for name, line1, line2 in records:
        if name.strip().lower() == target:
            return name, line1, line2
    return records[0]


def _interpolate_crossing(t_prev: datetime, t_curr: datetime, alt_prev: float, alt_curr: float) -> datetime:
    span = (t_curr - t_prev).total_seconds()
    if span <= 0 or alt_curr == alt_prev:
        return t_curr
    fraction = -alt_prev / (alt_curr - alt_prev)
    fraction = max(0.0, min(1.0, fraction))
    return t_prev + timedelta(seconds=span * fraction)


def compute_passes(
    satellite: EarthSatellite,
    station: GroundStation,
    ts,
    start_time: datetime,
    horizon_hours: float = 24.0,
    minimum_elevation_deg: float = 10.0,
    step_seconds: int = 30,
):
    total_steps = int((horizon_hours * 3600) // step_seconds) + 2
    step = timedelta(seconds=step_seconds)
    topos = wgs84.latlon(station.latitude_deg, station.longitude_deg, elevation_m=station.altitude_m)

    passes: list[PassWindow] = []
    in_pass = False
    pass_start: datetime | None = None
    pass_peak_time: datetime | None = None
    pass_peak_alt = float("-inf")

    prev_time = start_time
    prev_alt: float | None = None
    current = start_time

    for _ in range(total_steps):
        t = ts.from_datetime(current)
        difference = (satellite - topos).at(t)
        alt, _, _ = difference.altaz()
        alt_deg = alt.degrees

        if prev_alt is not None:
            if not in_pass and prev_alt < 0.0 <= alt_deg:
                rise = _interpolate_crossing(prev_time, current, prev_alt, alt_deg)
                in_pass = True
                pass_start = rise
                pass_peak_time = rise
                pass_peak_alt = -90.0
            elif in_pass and alt_deg < 0.0 <= prev_alt:
                set_time = _interpolate_crossing(prev_time, current, prev_alt, alt_deg)
                if pass_start and pass_peak_time and pass_peak_alt >= minimum_elevation_deg:
                    passes.append(
                        PassWindow(
                            start_utc=pass_start,
                            end_utc=set_time,
                            peak_utc=pass_peak_time,
                            max_elevation_deg=pass_peak_alt,
                            ground_station=station,
                        )
                    )
                in_pass = False
                pass_start = None
                pass_peak_time = None
                pass_peak_alt = float("-inf")

        if in_pass and alt_deg > pass_peak_alt:
            pass_peak_alt = alt_deg
            pass_peak_time = current

        prev_time = current
        prev_alt = alt_deg
        current += step

    return passes


def collect_passes(satellite: EarthSatellite, station: GroundStation, ts, start_time: datetime, limit: int = 3):
    horizon_hours = 24.0
    collected: list[PassWindow] = []

    while len(collected) < limit and horizon_hours <= 96.0:
        collected = compute_passes(satellite, station, ts, start_time, horizon_hours)
        if len(collected) >= limit:
            break
        horizon_hours *= 1.5

    collected.sort(key=lambda window: window.start_utc)
    return collected[:limit]


def print_report(
    mode: str,
    tle_name: str,
    norad_id: str,
    line1: str,
    line2: str,
    station: GroundStation,
    passes: Sequence[PassWindow],
) -> None:
    print(f"HoneySat link mode : {mode.upper()}")
    print(tle_name)
    print("=" * len(tle_name))
    print(f"NORAD catalog ID : {norad_id}")
    print()

    print("Two-Line Elements")
    print("-----------------")
    print(f"  {line1}")
    print(f"  {line2}")
    print()

    print("Ground Station")
    print("---------------")
    print(f"{station.name} ({station.location})")
    print(
        f"  Lat/Lon/Alt : {station.latitude_deg:.4f}°, {station.longitude_deg:.4f}°, {station.altitude_m:.0f} m"
    )
    print()

    print("Upcoming Passes")
    print("----------------")
    if not passes:
        print("No visible passes found in the planning window.")
        return

    for idx, window in enumerate(passes, start=1):
        start_str = window.start_utc.strftime("%Y-%m-%d %H:%M:%SZ")
        end_str = window.end_utc.strftime("%H:%M:%SZ")
        peak_str = window.peak_utc.strftime("%H:%M:%SZ")
        print(
            f"Pass {idx}: {start_str} → {end_str} | peak {window.max_elevation_deg:.1f}° at {peak_str}"
        )


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Predict HoneySat passes for a satellite over a single ground station.",
    )
    parser.add_argument(
        "mode",
        choices=("csp", "ccsds"),
        help="HoneySat link mode to plan for (csp or ccsds)",
    )
    parser.add_argument("name", help="Satellite name to query from CelesTrak")
    parser.add_argument(
        "station_location",
        help="Location string to geocode into a ground station",
    )
    return parser.parse_args(argv)


def _update_env_file(path: Path, updates: dict[str, str]) -> None:
    """Update KEY=VALUE pairs in an env file while preserving unrelated lines."""
    seen: set[str] = set()
    output_lines: list[str] = []

    if path.exists():
        for raw in path.read_text(encoding="utf-8").splitlines():
            stripped = raw.strip()
            if not stripped or stripped.startswith("#") or "=" not in raw:
                output_lines.append(raw)
                continue

            key, _, _ = raw.partition("=")
            key = key.strip()
            seen.add(key)

            if key in updates:
                output_lines.append(f"{key}={updates[key]}")
            else:
                output_lines.append(raw)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)

    for key, value in updates.items():
        if key not in seen:
            output_lines.append(f"{key}={value}")

    path.write_text("\n".join(output_lines) + ("\n" if output_lines else ""), encoding="utf-8")


def _start_system(start_args: Sequence[str]) -> int:
    launcher = Path(__file__).with_name("launch_honeysat.py")
    if not launcher.exists():
        print(f"Launcher script not found at {launcher}.", file=sys.stderr)
        return 6

    cmd = [sys.executable, str(launcher), *start_args]
    try:
        result = subprocess.run(cmd, check=False)
    except OSError as exc:
        print(f"Unable to execute launcher script: {exc}", file=sys.stderr)
        return 7
    return result.returncode


def _stop_system(stop_args: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog=f"{Path(__file__).name} stop",
        description="Stop HoneySat docker compose services.",
    )
    parser.add_argument(
        "mode",
        choices=("csp", "ccsds"),
        help="HoneySat stack to stop (csp or ccsds)",
    )
    parser.add_argument(
        "--compose-binary",
        default="docker",
        help="Compose-capable container engine to use (default: docker)",
    )
    parser.add_argument(
        "--profile",
        dest="profiles",
        action="append",
        help="Compose profile to include when stopping (defaults to ALL). Repeat to add multiple.",
    )
    args = parser.parse_args(stop_args)

    compose_file = Path(__file__).with_name(f"docker-compose-{args.mode}.yaml")
    if not compose_file.exists():
        print(f"Compose file not found for mode '{args.mode}' at {compose_file}.", file=sys.stderr)
        return 6

    profiles = args.profiles or ["ALL"]
    cmd = [args.compose_binary, "compose", "--file", str(compose_file)]
    for profile in profiles:
        cmd.extend(("--profile", profile))
    cmd.extend(("down", "--remove-orphans"))

    try:
        result = subprocess.run(cmd, check=False)
    except OSError as exc:
        print(f"Unable to execute compose binary '{args.compose_binary}': {exc}", file=sys.stderr)
        return 7
    return result.returncode


def main(argv: Sequence[str] | None = None) -> int:
    raw_args = list(argv or sys.argv[1:])
    if raw_args and raw_args[0] == "start":
        return _start_system(raw_args[1:])
    if raw_args and raw_args[0] == "stop":
        return _stop_system(raw_args[1:])

    args = parse_args(raw_args)

    try:
        label, lat, lon = geocode_location(args.station_location)
    except LookupError as exc:
        print(str(exc), file=sys.stderr)
        return 3

    station = GroundStation(
        identifier=_normalize_identifier(label),
        name=label,
        location=label,
        latitude_deg=lat,
        longitude_deg=lon,
    )

    try:
        tle_name, line1, line2 = fetch_tle_for_name(args.name)
    except LookupError as exc:
        print(str(exc), file=sys.stderr)
        return 4

    norad_id = line1[2:7].strip()

    ts = load.timescale()
    try:
        satellite = EarthSatellite(line1, line2, tle_name, ts)
    except ValueError as exc:
        print(f"TLE parsing failed: {exc}", file=sys.stderr)
        return 5

    now = datetime.now(timezone.utc)
    passes = collect_passes(satellite, station, ts, now, limit=3)
    print_report(args.mode, tle_name, norad_id, line1, line2, station, passes)
    # Also propagate the selected satellite name/ID to local env files so that
    # the running stacks and web UIs expose the same identity shown here.
    script_dir = Path(__file__).resolve().parent
    try:
        _update_env_file(
            script_dir / "honeysat-api.env",
            {
                "SATELLITE_NAME_TLE": tle_name,
                "SATELLITE_NORAD_CATALOG_NUMBER": norad_id,
            },
        )
        _update_env_file(
            script_dir / "csp_webpage.env",
            {
                # Title and visible labels in the web UI
                "MISSION_NAME": tle_name,
                "ENTITY_NAME": f"{tle_name} Operators",
                "SATELLITE_NAME_TLE": tle_name,
            },
        )
        # Keep input.env helpful for other tools (e.g., predictors)
        _update_env_file(
            script_dir / "input.env",
            {
                "SATELLITE_NORAD": norad_id,
            },
        )
        print()
        print("Updated env files with the selected satellite:")
        print(f"  - honeysat-api.env: SATELLITE_NAME_TLE={tle_name}, SATELLITE_NORAD_CATALOG_NUMBER={norad_id}")
        print(
            "  - csp_webpage.env : "
            f"MISSION_NAME={tle_name}, ENTITY_NAME={tle_name} Operators, SATELLITE_NAME_TLE={tle_name}"
        )
    except Exception as exc:
        # Non-fatal: printing the report remains useful even if env updates fail
        print(f"Warning: failed to update env files: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main())

#!/usr/bin/env python3
"""Configure and launch HoneySat experiment 3 services."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, Sequence

from honeysat import fetch_tle_for_name, geocode_location


SCRIPT_DIR = Path(__file__).resolve().parent
COMPOSE_FILES = {
    "csp": SCRIPT_DIR / "docker-compose-csp.yaml",
    "ccsds": SCRIPT_DIR / "docker-compose-ccsds.yaml",
}
DEFAULT_PROFILES = ("ALL",)


class LauncherError(RuntimeError):
    """Raised when preparing or launching the stack fails."""


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Configure HoneySat images and launch the requested stack.",
    )
    parser.add_argument(
        "mode",
        choices=sorted(COMPOSE_FILES),
        help="Stack to start (matches the first positional argument of honeysat.py)",
    )
    parser.add_argument("name", help="Satellite name to fetch from CelesTrak")
    parser.add_argument(
        "station_location",
        help="Ground station location string (same as honeysat.py positional station argument)",
    )
    parser.add_argument(
        "--compose-binary",
        default="docker",
        help="Compose binary to invoke (default: docker). Set to 'docker' or 'podman'.",
    )
    return parser.parse_args(argv)


def _update_env_file(path: Path, updates: Dict[str, str]) -> None:
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


def _configure_environment(
    mode: str,
    tle_name: str,
    norad_id: str,
    latitude: float,
    longitude: float,
) -> Iterable[Path]:
    """Write the env files required by the compose stacks."""
    lat_str = f"{latitude:.6f}"
    lon_str = f"{longitude:.6f}"

    written_paths: list[Path] = []

    honeysat_api_env = SCRIPT_DIR / "honeysat-api.env"
    _update_env_file(
        honeysat_api_env,
        {
            "GROUND_STATION_LAT": lat_str,
            "GROUND_STATION_LON": lon_str,
            "SATELLITE_NAME_TLE": tle_name,
            "SATELLITE_NORAD_CATALOG_NUMBER": norad_id,
        },
    )
    written_paths.append(honeysat_api_env)

    # Input env helps auxiliary tooling such as predictors.
    input_env = SCRIPT_DIR / "input.env"
    _update_env_file(
        input_env,
        {
            "SATELLITE_NORAD": norad_id,
        },
    )
    written_paths.append(input_env)

    honeysat_web_env = SCRIPT_DIR / "honeysat-webpage-v2.env"
    _update_env_file(
        honeysat_web_env,
        {
            "GROUND_STATION_LAT": lat_str,
            "GROUND_STATION_LON": lon_str,
        },
    )
    written_paths.append(honeysat_web_env)

    # The CSP stack uses csp_webpage.env; keep the file updated even if mode == ccsds.
    csp_web_env = SCRIPT_DIR / "csp_webpage.env"
    _update_env_file(
        csp_web_env,
        {
            "SATELLITE_NAME_TLE": tle_name,
        },
    )
    written_paths.append(csp_web_env)

    return written_paths


def _run_compose(
    compose_binary: str,
    compose_file: Path,
    *args: str,
    profiles: Sequence[str] = DEFAULT_PROFILES,
) -> None:
    cmd = [compose_binary, "compose", "--file", str(compose_file)]
    for profile in profiles:
        cmd.extend(("--profile", profile))
    cmd.extend(args)
    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError as exc:
        raise LauncherError(f"Compose binary '{compose_binary}' not found.") from exc
    except subprocess.CalledProcessError as exc:
        raise LauncherError(f"Command {' '.join(cmd)} failed with exit code {exc.returncode}.") from exc


def launch(args: argparse.Namespace) -> None:
    compose_file = COMPOSE_FILES.get(args.mode)
    if compose_file is None or not compose_file.exists():
        raise LauncherError(f"No compose file found for mode '{args.mode}'.")

    try:
        geocode_label, latitude, longitude = geocode_location(args.station_location)
    except LookupError as exc:
        raise LauncherError(f"Failed to geocode location '{args.station_location}': {exc}") from exc

    try:
        tle_name, line1, _ = fetch_tle_for_name(args.name)
    except LookupError as exc:
        raise LauncherError(f"Failed to retrieve TLE for '{args.name}': {exc}") from exc

    norad_id = line1[2:7].strip()

    updated_files = _configure_environment(
        args.mode,
        tle_name,
        norad_id,
        latitude,
        longitude,
    )

    print(f"Configured ground station '{geocode_label}' ({latitude:.4f}, {longitude:.4f}).")
    print(f"Resolved satellite '{tle_name}' with NORAD ID {norad_id}.")
    print("Updated configuration files:")
    for path in updated_files:
        rel = path.relative_to(SCRIPT_DIR)
        print(f"  - {rel}")

    print(f"Rebuilding containers for mode '{args.mode}'...")
    _run_compose(args.compose_binary, compose_file, "build", "--pull")

    print("Stopping any previous services for a clean restart...")
    _run_compose(args.compose_binary, compose_file, "down", "--remove-orphans")

    print("Recreating and starting services...")
    _run_compose(args.compose_binary, compose_file, "up", "--build", "--force-recreate", "-d")

    print("HoneySat services are up and running.")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        launch(args)
    except LauncherError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

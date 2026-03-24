#!/usr/bin/env bash

# Exit on error, undefined variable usage, or pipeline failures
set -euo pipefail

# --- Defaults & helpers ------------------------------------------------------
DEFAULT_NORAD_NUMBER="62171"
DEFAULT_MINUTES_AHEAD="7"

usage() {
    cat <<EOF
Usage: $(basename "$0") [NORAD_NUMBER MINUTES_AHEAD]

Run experiment 2 for HoneySat using the Yamcs docker compose stack.

Arguments:
  NORAD_NUMBER   NORAD catalog number to predict (default: ${DEFAULT_NORAD_NUMBER})
  MINUTES_AHEAD  Minutes in the future to predict (default: ${DEFAULT_MINUTES_AHEAD})

The script requires an active Python virtual environment that already has the
dependencies from python_ground_station_predictor/requirements.txt installed.

Examples:
  $(basename "$0")
  $(basename "$0") 25544 10

Use --help or -h to display this message.
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    usage
    exit 0
fi

case "$#" in
    0)
        NORAD_NUMBER="${DEFAULT_NORAD_NUMBER}"
        MINUTES_AHEAD="${DEFAULT_MINUTES_AHEAD}"
        using_defaults=true
        ;;
    2)
        NORAD_NUMBER="$1"
        MINUTES_AHEAD="$2"
        using_defaults=false
        ;;
    *)
        echo "Error: expected either zero or two positional arguments." >&2
        usage >&2
        exit 1
        ;;
esac

if ! [[ "${NORAD_NUMBER}" =~ ^[0-9]+$ ]]; then
    echo "Error: NORAD_NUMBER must be a positive integer (received '${NORAD_NUMBER}')." >&2
    usage >&2
    exit 1
fi

if ! [[ "${MINUTES_AHEAD}" =~ ^-?[0-9]+$ ]]; then
    echo "Error: MINUTES_AHEAD must be an integer (received '${MINUTES_AHEAD}')." >&2
    usage >&2
    exit 1
fi

if [[ "${using_defaults}" == "true" ]]; then
    echo "Using default NORAD ${NORAD_NUMBER} and lead time ${MINUTES_AHEAD} minute(s)."
fi

# --- Virtual environment guard -----------------------------------------------
if [[ -z "${VIRTUAL_ENV:-}" && -z "${CONDA_PREFIX:-}" ]]; then
    echo "Error: No Python virtual environment detected. Activate the appropriate venv or conda environment before running this script."
    exit 1
fi

# --- Cleanup handling --------------------------------------------------------
services_started=false
cleanup_done=false

cleanup() {
    if [[ "${cleanup_done}" == "true" ]]; then
        return
    fi
    cleanup_done=true

    if [[ "${services_started}" == "true" ]]; then
        echo "Stopping docker compose services..."
        set +e
        "${DOCKER_COMPOSE_CMD[@]}" down -v
        local status=$?
        set -e
        if [[ ${status} -ne 0 ]]; then
            echo "Warning: docker compose down exited with status ${status}." >&2
        fi
        services_started=false
    fi
}

on_exit() {
    cleanup
}

on_signal() {
    echo
    echo "Signal received. Cleaning up..."
    cleanup
    exit 0
}

# --- Setup paths -------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/docker-compose-ccsds.yaml"
PREDICTOR="${SCRIPT_DIR}/python_ground_station_predictor/ground_station_predictor.py"
REQUIREMENTS_FILE="${SCRIPT_DIR}/python_ground_station_predictor/requirements.txt"
YAMCS_CALLER="${SCRIPT_DIR}/python_yamcs_api/python_yamcs_caller.py"

if [[ ! -f "${COMPOSE_FILE}" ]]; then
    echo "Error: docker compose file not found at ${COMPOSE_FILE}"
    exit 1
fi

if [[ ! -f "${PREDICTOR}" ]]; then
    echo "Error: predictor script not found at ${PREDICTOR}"
    exit 1
fi

if [[ ! -f "${REQUIREMENTS_FILE}" ]]; then
    echo "Error: requirements file not found at ${REQUIREMENTS_FILE}"
    exit 1
fi

if [[ ! -f "${YAMCS_CALLER}" ]]; then
    echo "Error: Yamcs caller script not found at ${YAMCS_CALLER}"
    exit 1
fi

DOCKER_COMPOSE_CMD=(docker compose --file "${COMPOSE_FILE}")

#trap on_exit EXIT
trap on_signal INT TERM

# --- Dependency check --------------------------------------------------------
echo "Validating Python requirements..."
if ! python3 - "${REQUIREMENTS_FILE}" <<'PY'
import sys
from pathlib import Path

try:
    from importlib import metadata
except ImportError:
    try:
        import importlib_metadata as metadata  # type: ignore
    except ImportError:
        print("Error: importlib.metadata (or importlib_metadata backport) is required to verify dependencies.")
        sys.exit(1)

def parse_requirement(raw: str):
    entry = raw.strip()
    if not entry or entry.startswith("#"):
        return None
    if "==" in entry:
        name, version = entry.split("==", 1)
        return name.strip(), version.strip()
    return entry, None

def main(req_path: Path) -> int:
    try:
        requirements = [
            parsed
            for raw in req_path.read_text(encoding="utf-8").splitlines()
            if (parsed := parse_requirement(raw)) is not None
        ]
    except FileNotFoundError:
        print(f"Error: requirements file '{req_path}' not found.")
        return 1

    if not requirements:
        return 0

    all_good = True
    for name, version in requirements:
        try:
            installed_version = metadata.version(name)
        except metadata.PackageNotFoundError:
            print(f"Missing dependency: {name}")
            all_good = False
            continue

        if version and installed_version != version:
            print(
                f"Version mismatch for {name}: installed {installed_version}, required {version}"
            )
            all_good = False

    return 0 if all_good else 1

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Internal error: requirements file argument missing.")
        sys.exit(1)
    sys.exit(main(Path(sys.argv[1])))
PY
then
    echo "Install missing dependencies with: python3 -m pip install -r \"${REQUIREMENTS_FILE}\""
    exit 1
fi
echo "Python requirements satisfied."

# --- Ensure docker images are available --------------------------------------
echo "Pulling docker images..."
"${DOCKER_COMPOSE_CMD[@]}" pull

# --- Build / prepare Docker images ------------------------------------------
echo "Building Docker images..."
"${DOCKER_COMPOSE_CMD[@]}" build

# --- Predict ground station position ----------------------------------------
echo "Running ground station predictor (NORAD: ${NORAD_NUMBER}, minutes ahead: ${MINUTES_AHEAD})..."
python3 "${PREDICTOR}" --norad "${NORAD_NUMBER}" --minutes "${MINUTES_AHEAD}"

# --- Launch services ---------------------------------------------------------
echo "Starting Yamcs docker compose services..."
services_started=true
"${DOCKER_COMPOSE_CMD[@]}" up -d

# --- Invoke Yamcs caller -----------------------------------------------------
echo "Waiting (10s) for YAMCS services to initialize..."
sleep 10
echo "Calling python_yamcs_caller.py..."
python3 "${YAMCS_CALLER}"

echo "All services are running. Press Ctrl+C to stop and clean up."

# Keep script running until interrupted so cleanup can occur
while true; do
    sleep 60
done

#!/usr/bin/env python3
"""
Issue ADCS fetch commands and print resulting telemetry.

Prereqs:
  pip install yamcs-client

Defaults target the Honeysat Yamcs stack (`docker-compose-ccsds.yaml`), which
requires authentication. Override connection details with the following
environment variables if needed:

  YAMCS_SERVER     (default: localhost:8090)
  YAMCS_INSTANCE   (default: satellite)
  YAMCS_PROCESSOR  (default: realtime)
  YAMCS_USERNAME   (default: administrator)
  YAMCS_PASSWORD   (default: Admin123)
  YAMCS_TM_PREFIX  (deprecated; single prefix override)
  YAMCS_TM_PREFIXES (default: /SERVICE-ADCS/,/SERVICE-EPS/,/SERVICE-OBC/)
  YAMCS_TM_PARAMETERS (default: ADCS/EPS/OBC telemetry list; comma-separated)
  YAMCS_TAIL_SECS  (default: 10)

The configured user must have the Yamcs `CommandOptions` system privilege.
"""

import os
import time
from typing import List, Tuple, Dict, Any, Optional
from yamcs.client import YamcsClient, VerificationConfig, Credentials

# ----------------- Config -----------------

SERVER = os.getenv("YAMCS_SERVER", "localhost:8090")
INSTANCE = os.getenv("YAMCS_INSTANCE", "satellite")
PROCESSOR = os.getenv("YAMCS_PROCESSOR", "realtime")
USERNAME = os.getenv("YAMCS_USERNAME", "administrator")
PASSWORD = os.getenv("YAMCS_PASSWORD", "Admin123")

def _csv_env(env_var: str, default: List[str]) -> List[str]:
    raw = os.getenv(env_var)
    if not raw:
        return default
    values = [item.strip() for item in raw.split(",")]
    return [value for value in values if value]

# Fully qualified command names as shown in your screenshot
COMMANDS: List[Tuple[str, Dict[str, Any]]] = [
    ("/SERVICE-ADCS/Fetch_ADCS_Gyro_Data", {}),
    ("/SERVICE-ADCS/Fetch_ADCS_Mag_Data",  {}),
    ("/SERVICE-ADCS/Fetch_ADCS_Sun_Data",  {}),
    ("/SERVICE-EPS/FetchEPSData", {}),
    ("/SERVICE-OBC/GetTemperature", {}),
]

# We’ll subscribe to these parameters and filter to the configured prefixes locally.
DEFAULT_TM_PARAMETERS = [
    "/SERVICE-ADCS/ADCS_GYRO_X",
    "/SERVICE-ADCS/ADCS_GYRO_Y",
    "/SERVICE-ADCS/ADCS_GYRO_Z",
    "/SERVICE-ADCS/ADCS_MAG_X",
    "/SERVICE-ADCS/ADCS_MAG_Y",
    "/SERVICE-ADCS/ADCS_MAG_Z",
    "/SERVICE-ADCS/ADCS_SUN",
    "/SERVICE-EPS/EPS_VOLTAGE",
    "/SERVICE-EPS/EPS_CURRENT_IN",
    "/SERVICE-EPS/EPS_CURRENT_OUT",
    "/SERVICE-EPS/EPS_TEMPERATURE",
    "/SERVICE-OBC/OBC_Temperature",
]
TM_PARAMETERS = _csv_env("YAMCS_TM_PARAMETERS", DEFAULT_TM_PARAMETERS)
if not TM_PARAMETERS:
    raise SystemExit(
        "No telemetry parameters specified. Set YAMCS_TM_PARAMETERS with at least one entry."
    )

def _prefix_list() -> List[str]:
    multi = os.getenv("YAMCS_TM_PREFIXES")
    if multi:
        prefixes = [item.strip() for item in multi.split(",") if item.strip()]
        if prefixes:
            return prefixes
    single = os.getenv("YAMCS_TM_PREFIX")
    if single:
        return [single]
    return ["/SERVICE-ADCS/", "/SERVICE-EPS/", "/SERVICE-OBC/"]

TM_PREFIXES = _prefix_list()

# How long to keep listening after the last command (seconds)
TAIL_SECS = int(os.getenv("YAMCS_TAIL_SECS", "10"))

# --------------- Script logic -------------

def main():
    creds: Optional[Credentials] = None
    if USERNAME:
        if not PASSWORD:
            raise SystemExit("YAMCS_USERNAME is set but YAMCS_PASSWORD is empty.")
        creds = Credentials(username=USERNAME, password=PASSWORD)

    identity = USERNAME or "(anonymous)"
    print(f"Connecting to Yamcs at {SERVER} (instance={INSTANCE}, processor={PROCESSOR}) as {identity}")

    client = YamcsClient(SERVER, credentials=creds)
    processor = client.get_processor(INSTANCE, PROCESSOR)

    # Print any matching telemetry as it arrives
    def on_tm(delivery):
        for p in delivery.parameters:
            pname = getattr(p, "name", None) or getattr(p, "parameter", None)
            if not isinstance(pname, str):
                qualified = getattr(pname, "qualifiedName", None)
                if not qualified and pname is not None:
                    base = getattr(pname, "name", None)
                    ns = getattr(pname, "namespace", None)
                    if base:
                        if ns:
                            prefix = ns if ns.startswith("/") else f"/{ns}"
                            qualified = f"{prefix}/{base}"
                        else:
                            qualified = base
                pname = qualified or str(p)

            if TM_PREFIXES and not any(pname.startswith(prefix) for prefix in TM_PREFIXES):
                continue

            eng = getattr(p, "eng_value", None) or getattr(p, "engValue", None)
            raw = getattr(p, "raw_value", None) or getattr(p, "rawValue", None)
            t = getattr(p, "generation_time", None) or getattr(p, "generationTime", None)
            if hasattr(t, "isoformat"):
                t = t.isoformat()
            print(f"[TM] {pname}  eng={eng}  raw={raw}  t={t}")

    # Subscribe to specific parameters and rely on prefix filtering for safety.
    try:
        sub = processor.create_parameter_subscription(
            TM_PARAMETERS, on_data=on_tm, send_from_cache=False
        )
    except Exception as exc:
        raise SystemExit(
            f"Failed to subscribe to telemetry {TM_PARAMETERS}: {exc}"
        ) from exc

    # Commanding connection (so we can await completion)
    conn = processor.create_command_connection()

    # Example: relax "Started" verification in case your commands don’t emit it
    verification = VerificationConfig()
    verification.disable("Started")

    # Issue each command and wait for completion
    for name, args in COMMANDS:
        print(f"[TC] Issuing {name} {args or ''}".strip())
        cmd = conn.issue(name, args=args, verification=verification)
        cmd.await_complete()
        if cmd.is_success():
            print(f"[TC] {name} completed OK")
        else:
            print(f"[TC] {name} FAILED: {cmd.error}")

    observed = ", ".join(TM_PREFIXES) if TM_PREFIXES else "all"
    print(f"Observing {observed} telemetry for {TAIL_SECS}s…")
    time.sleep(TAIL_SECS)

    sub.cancel()
    print("Done.")

if __name__ == "__main__":
    main()

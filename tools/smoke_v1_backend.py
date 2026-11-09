"""Start the fixture API on loopback, check HTTP responses, and stop it."""

import json
import os
from contextlib import closing
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]


def check_once(database_path, extra_check=None):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    env = dict(os.environ, ARCSHIFT_ENVIRONMENT="test", ARCSHIFT_DATA_MODE="synthetic", ARCSHIFT_HOST="127.0.0.1", ARCSHIFT_PORT=str(port), ARCSHIFT_STORAGE_BACKEND="sqlite", ARCSHIFT_DB_PATH=str(database_path), PYTHONDONTWRITEBYTECODE="1")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    process = subprocess.Popen(
        [sys.executable, "-m", "arcshift_v1"], cwd=ROOT, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    base = f"http://127.0.0.1:{port}"
    checked = []

    def get(path):
        with opener.open(base + path, timeout=2) as response:
            if response.status != 200 or response.headers.get("X-ArcShift-Data-Mode") != "synthetic":
                raise RuntimeError("Unexpected fixture response or missing synthetic header")
            payload = json.load(response)
        checked.append(path)
        return payload

    try:
        deadline = time.monotonic() + 15
        while True:
            if process.poll() is not None:
                raise RuntimeError("Fixture server exited before readiness")
            try:
                health = get("/healthz")
                break
            except (urllib.error.URLError, TimeoutError, OSError):
                if time.monotonic() >= deadline:
                    raise RuntimeError("Fixture server startup timed out") from None
                time.sleep(0.1)
        if health["production_ready"] or health["readiness_scope"] != "fixture_development_only":
            raise RuntimeError("Fixture startup claimed production readiness")
        get("/readyz")
        scenarios = get("/api/v1/demo/scenarios")
        if len(scenarios["scenarios"]) != 6 or scenarios["synthetic"] is not True:
            raise RuntimeError("Unexpected scenario collection")
        if get("/api/v1/demo/scenarios/stale")["scenario"]["signal"] is not None:
            raise RuntimeError("Stale scenario unexpectedly contains a risk score")
        demo = get("/api/v1/demo/scenarios/historical_demo")["scenario"]["signal"]
        if demo["score_kind"] != "synthetic_uncalibrated_score":
            raise RuntimeError("Demo score lost its synthetic label")
        market = get("/api/v1/market/series")
        if len(market["series"]) != 7 or market["validity_status"] != "historical_demo" or market["source_rights_status"] != "not_admitted":
            raise RuntimeError("Market history lost its synthetic boundary")
        history = get("/api/v1/market/series/ru.fx.cbr.usd_rub.official/history?include_revisions=true")
        if history["total"] != 4 or history["observations"][-1]["observation"]["value"] != 81.2 or any(row["observation"]["published_at"] is not None for row in history["observations"]):
            raise RuntimeError("Parser history or unknown publication metadata changed")
        profile = get("/api/v1/models/status")
        task = get("/api/v1/models/task")
        measurement = get("/api/v1/models/measurement")
        if task["task_id"] != profile["task_id"] or task["primary_horizon_days"] != 30 or task["measurement_status"] != "design_frozen_not_validated" or task["production_ready"]:
            raise RuntimeError("Business task approval lost its model-admission boundary")
        if profile["measurement_sha256"] != measurement["measurement_sha256"] or measurement["definition"]["empirical_validity_established"]:
            raise RuntimeError("Measurement contract mismatch or unjustified empirical validation")
        current = get("/api/v1/signals/current")
        if profile["accepted_artifact_available"] or current["signal"] is not None or current["state"] != "unavailable" or profile["data_snapshot_id"] != current["data_snapshot_id"]:
            raise RuntimeError("Unapproved model unexpectedly served a prediction")
        get("/openapi.json")
        if extra_check is not None:
            extra_check(base)
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        log = process.communicate(timeout=5)[0]
        if process.returncode not in (0, -15):
            print(log, file=sys.stderr)
    if process.returncode not in (0, -15):
        raise RuntimeError("Fixture server did not stop cleanly")
    return {"status": "ok", "checked_paths": checked, "data_mode": "synthetic", "production_ready": False, "server_stopped_after_check": process.poll() is not None}


def persisted_state(path):
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as connection:
        return (
            connection.execute("SELECT * FROM schema_migrations ORDER BY version").fetchall(),
            connection.execute("SELECT * FROM fixture_snapshots ORDER BY snapshot_id").fetchall(),
            connection.execute("SELECT * FROM fixture_active_snapshot").fetchall(),
            connection.execute("SELECT * FROM local_market_snapshots").fetchall(),
            connection.execute("SELECT * FROM local_market_active").fetchall(),
        )


def smoke():
    with TemporaryDirectory(prefix="arcshift-v1-smoke-") as directory:
        path = Path(directory) / "fixture.sqlite3"
        first = check_once(path)
        state = persisted_state(path)
        second = check_once(path)
        if state != persisted_state(path) or len(state[1]) != 1:
            raise RuntimeError("Fixture snapshot or migration history changed after process restart")
        return {
            **second,
            "storage_backend": "sqlite",
            "startup_cycles": 2,
            "snapshot_count": 1,
            "persistence_across_restart_verified": True,
            "server_stopped_after_check": first["server_stopped_after_check"] and second["server_stopped_after_check"],
        }


if __name__ == "__main__":
    print(json.dumps(smoke(), ensure_ascii=False, indent=2))

"""Shared, explicitly isolated test environment helpers. Never targets production."""

import json
import subprocess
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
DIN = "leroy-test-docker-1"


def inner(*args, **kwargs):
    result = subprocess.run(
        ["docker", "exec", DIN, "docker", *map(str, args)],
        check=False,
        text=True,
        capture_output=True,
        **kwargs,
    )
    if result.returncode:
        # Docker arguments and output can contain freshly generated test secrets.
        raise RuntimeError(f"Isolated Docker command failed (exit {result.returncode})")
    return result.stdout.strip()


def api():
    client = httpx.Client(base_url="http://127.0.0.1:8088", headers={"X-Leroy-Request": "1"}, timeout=60)
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": (ROOT / ".local/admin_password").read_text().strip()},
    )
    response.raise_for_status()
    return client


def start(client, pipeline, parameters=None, commit=None):
    response = client.post(
        f"/api/pipelines/{pipeline}/runs", json={"parameters": parameters or {}, "commit": commit}
    )
    response.raise_for_status()
    return response.json()["id"]


def wait(client, run_id, timeout=300):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        response = client.get("/api/runs/" + run_id)
        response.raise_for_status()
        run = response.json()
        if run["status"] not in ("queued", "running", "waiting"):
            return run
        time.sleep(1)
    raise TimeoutError(run_id)


def evidence(client, run_id):
    run = client.get("/api/runs/" + run_id).json()
    directory = ROOT / "test-results/migrations" / run["pipeline_id"] / run_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "run.json").write_text(json.dumps(run, indent=2), encoding="utf-8")
    for step in run["steps"]:
        offset = 0
        with (directory / (step["id"] + ".log")).open("w", encoding="utf-8") as stream:
            while offset < step["log_bytes"]:
                log = client.get(f"/api/runs/{run_id}/logs/{step['id']}", params={"offset": offset}).json()
                stream.write(log.get("text", ""))
                if log.get("next_offset", offset) <= offset:
                    break
                offset = log["next_offset"]
    return run

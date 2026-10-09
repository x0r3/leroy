"""Trusted Docker supervisor. Repository code only runs inside job containers."""

import json
import os
import re
import signal
import socket
import subprocess
import tempfile
import threading
import time
import tomllib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from .config import secret


def docker(*args, **kwargs):
    kwargs.setdefault("timeout", 30)
    return subprocess.run(["docker", *map(str, args)], check=True, capture_output=True, text=True, **kwargs)


def cleanup_finished_run(run_id):
    """Reap a controller-authorized terminal attempt, including its nested helpers."""
    if not re.fullmatch(r"[a-f0-9]{32}", run_id):
        raise ValueError("Invalid run identity for cleanup")
    name = "leroy-" + run_id
    # Stop the owner before enumerating helpers so it cannot create more. Keep
    # its container as a retry anchor until all helper removals have succeeded.
    docker("stop", "--time", "5", name)
    rows = docker("ps", "-a", "--filter", "label=io.leroy.run=" + run_id,
                  "--format", "{{.ID}} {{.Names}}").stdout.splitlines()
    for row in rows:
        container, container_name = row.split(" ", 1)
        if container_name != name:
            docker("rm", "-f", "-v", container)
    docker("rm", "-f", "-v", name)
    docker("volume", "rm", name + "-work")


def main():
    config = tomllib.loads(Path(os.environ.get("LEROY_RUNNER_CONFIG", "/config/runner.toml")).read_text())
    url = os.environ["LEROY_CONTROLLER"].rstrip("/")
    token = secret("LEROY_RUNNER_TOKEN")
    runner_id = os.environ.get("LEROY_RUNNER_ID", socket.gethostname())
    capacity = config.get("capacity", 2)
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    client = httpx.Client(headers={"Authorization": "Bearer " + token}, timeout=30)

    def launch(run):
        name = "leroy-" + run["id"]
        volume = name + "-work"
        try:
            profile = dict(config["profiles"][run["snapshot"]["profile"]])
            secrets_data = {}
            file_secrets = {}
            needed = {name for s in run["snapshot"]["steps"] for name in s.get("secrets", [])}
            defaults = {p["name"]: p.get("default") for p in run["snapshot"].get("parameters", [])}
            configured = dict(profile.get("secrets", {}))
            for group, selectors in run["snapshot"].get("credential_parameters", {}).items():
                if group not in needed:
                    continue
                fields = dict(configured.get(group, {}))
                for parameter in selectors:
                    selected = run["parameters"].get(parameter)
                    if selected != defaults.get(parameter):
                        if not selected and group in ("git", "registry"):
                            fields.clear()
                            continue
                        override = profile.get("credential_overrides", {}).get(group, {}).get(selected)
                        if override is None:
                            raise ValueError("Unconfigured credential reference for " + parameter)
                        fields.update(override)
                configured[group] = fields
            for group, fields in configured.items():
                if group in needed:
                    secrets_data[group] = {}
                    for key, value in fields.items():
                        content = Path(value).read_text().strip()
                        if key.endswith(("_FILE", "_KEY", "KNOWN_HOSTS")):
                            filename = group + "-" + key
                            file_secrets[filename] = content + "\n"
                            secrets_data[group][key] = "/job/credentials/" + filename
                        else:
                            secrets_data[group][key] = content
            profile["secrets"] = secrets_data
            image = profile.get("image", "leroy-job:local")
            image_id = docker("image", "inspect", image, "--format", "{{.Id}}").stdout.strip()
            with tempfile.TemporaryDirectory(prefix="leroy-assignment-") as folder:
                folder = Path(folder)
                (folder / "assignment.json").write_text(
                    json.dumps({k: v for k, v in run.items() if k != "token"})
                )
                (folder / "credentials").mkdir()
                for filename, value in file_secrets.items():
                    path = folder / "credentials" / filename
                    path.write_text(value)
                    path.chmod(0o600)
                args = [
                    "create",
                    "--name",
                    name,
                    "--label",
                    "io.leroy.run=" + run["id"],
                    "--label",
                    "io.leroy.runner=" + runner_id,
                    "--init",
                    "--memory",
                    profile.get("memory", "4g"),
                    "--cpus",
                    str(profile.get("cpus", 2)),
                    "--pids-limit",
                    str(profile.get("pids_limit", 1024)),
                    "--cap-drop",
                    "ALL",
                    "--security-opt",
                    "no-new-privileges:true",
                    "--network",
                    profile.get("network", "leroy-jobs"),
                    "--mount",
                    f"type=volume,source={volume},target=/work",
                    "--env",
                    "LEROY_CONTROLLER=" + url,
                    "--env",
                    "LEROY_ATTEMPT_TOKEN=" + run["token"],
                ]
                if profile.get("memory_reservation"):
                    args += ["--memory-reservation", str(profile["memory_reservation"])]
                if profile.get("memory_swap"):
                    args += ["--memory-swap", str(profile["memory_swap"])]
                # Normally use Docker/external DNS, which survives controller replacement.
                # Nested test daemons may supply an explicitly stable gateway mapping.
                for host, address in profile.get("host_mappings", {}).items():
                    args += ["--add-host", host + ":" + address]
                for mount in profile.get("mounts", []):
                    args += ["--mount", mount]
                # Docker access is a trusted profile capability, never a parameter supplied by a job.
                if profile.get("docker", False):
                    args += ["--mount", "type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock"]
                for key, value in profile.get("environment", {}).items():
                    args += ["--env", str(key) + "=" + str(value)]
                docker(*args, image_id, "python", "-m", "leroy.worker")
                profile["host_workspace"] = docker(
                    "volume", "inspect", volume, "--format", "{{.Mountpoint}}"
                ).stdout.strip()
                (folder / "profile.json").write_text(json.dumps(profile))
                docker("cp", str(folder) + "/.", name + ":/job")
                response = client.post(
                    url + "/internal/runs/" + run["id"] + "/identity",
                    headers={"Authorization": "Bearer " + run["token"]},
                    json={"image_digest": image_id},
                )
                response.raise_for_status()
                docker("start", name)
            # Workers own their lease and report completion. Startup threads must not
            # remain occupied while parents wait for children to acquire capacity.
        except Exception as exc:
            try:
                client.post(
                    url + "/internal/runs/" + run["id"] + "/complete",
                    headers={"Authorization": "Bearer " + run["token"]},
                    json={
                        "status": "failed",
                        "reason": "Runner infrastructure failure: " + type(exc).__name__,
                    },
                )
            except Exception:
                pass
            print("Runner execution failed:", type(exc).__name__, flush=True)
            # Only resources bearing this exact run name are owned by this supervisor.
            for command in (("rm", "-f", "-v", name), ("volume", "rm", volume)):
                try:
                    docker(*command)
                except subprocess.SubprocessError:
                    print("Runner cleanup deferred:", name, flush=True)

    def reap_finished():
        """Recover containers whose supervising process was restarted mid-run."""
        names = docker(
            "ps", "-a", "--filter", "label=io.leroy.runner=" + runner_id, "--format", "{{.Names}}"
        ).stdout.split()
        if not names:
            return
        for offset in range(0, len(names), 100):
            # Inspect only the state, never environment variables containing attempt tokens.
            batch = names[offset : offset + 100]
            states = docker("inspect", "--format", "{{.Name}} {{json .State}}", *batch).stdout.splitlines()
            ids = []
            for line in states:
                name, state = line.split(" ", 1)
                name, state = name.lstrip("/"), json.loads(state)
                id = name.removeprefix("leroy-")
                ids.append(id)
                if state["Status"] in ("exited", "dead"):
                    response = client.post(
                        url + "/internal/exited",
                        json={"runner": runner_id, "run_id": id, "exit_code": state["ExitCode"]},
                    )
                    response.raise_for_status()
            response = client.post(url + "/internal/reap", json={"runner": runner_id, "run_ids": ids})
            response.raise_for_status()
            for id in response.json():
                name = "leroy-" + id
                if name in batch:
                    cleanup_finished_run(id)

    with ThreadPoolExecutor(max_workers=capacity) as pool:
        futures = []
        next_reap = 0
        while not stop.is_set():
            futures = [f for f in futures if not f.done()]
            try:
                if time.monotonic() >= next_reap:
                    reap_finished()
                    next_reap = time.monotonic() + 5
                if len(futures) >= capacity:
                    stop.wait(1)
                    continue
                response = client.post(
                    url + "/internal/claim",
                    json={"runner": runner_id, "profiles": list(config["profiles"]), "capacity": capacity},
                )
                response.raise_for_status()
                run = response.json()
                if run:
                    futures.append(pool.submit(launch, run))
            except (httpx.HTTPError, ValueError, subprocess.SubprocessError):
                pass
            stop.wait(1)


if __name__ == "__main__":
    main()

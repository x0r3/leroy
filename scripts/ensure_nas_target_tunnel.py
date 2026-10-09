"""Restore and supervise only the existing key-pinned test-VM reverse tunnel."""

import argparse
import ctypes
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone

from deploy_nas_parity import LOCAL

FOLDER = LOCAL / "vm"
STATE = FOLDER / "tunnel.json"
KEEP = FOLDER / "tunnel.keepalive"


def alive(pid):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = ctypes.c_void_p
    handle = kernel.OpenProcess(0x1000, False, int(pid))
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        return (
            bool(kernel.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code))) and code.value == 259
        )
    finally:
        kernel.CloseHandle(ctypes.c_void_p(handle))


def supervise(maximum_hours, generation):
    deadline = time.monotonic() + maximum_hours * 3600
    command = [
        "ssh",
        "-N",
        "-T",
        "-i",
        str(FOLDER / "tunnel-key"),
        "-p",
        "12226",
        "-o",
        "UserKnownHostsFile=" + str(FOLDER / "tunnel-known-hosts"),
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "ServerAliveInterval=15",
        "-o",
        "ServerAliveCountMax=3",
        "-o",
        "ExitOnForwardFailure=yes",
        "-R",
        "10.232.98.11:12225:127.0.0.1:2225",
        "root@192.168.178.97",
    ]
    attempts = 0
    with (FOLDER / "tunnel-supervised.log").open("ab", buffering=0) as log:
        while KEEP.exists() and time.monotonic() < deadline:
            attempts += 1
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            try:
                time.sleep(3)
                data = {
                    "pid": process.pid,
                    "supervisor_pid": os.getpid(),
                    "remote_port": 12225,
                    "local_port": 2225,
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "attempt": attempts,
                    "connected_process_alive": process.poll() is None,
                    "maximum_supervision_hours": maximum_hours,
                    "generation": generation,
                }
                temporary = STATE.with_suffix(".next")
                temporary.write_text(json.dumps(data) + "\n")
                temporary.replace(STATE)
                while process.poll() is None and KEEP.exists() and time.monotonic() < deadline:
                    time.sleep(3)
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=10)
            time.sleep(5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--supervise", action="store_true")
    modes.add_argument("--renew", action="store_true", help="Renew while no jobs use the test VM")
    parser.add_argument("--hours", type=int, choices=range(1, 25), default=6)
    parser.add_argument("--generation", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.supervise:
        supervise(args.hours, args.generation or uuid.uuid4().hex)
        return
    previous = json.loads(STATE.read_text())
    if args.renew:
        from contextlib import closing

        from compare_nas_antares import client
        from nas_followup_support import inner, jenkins_api

        with closing(client()) as api:
            for status in ("queued", "running", "waiting"):
                response = api.get("/api/runs", params={"status": status})
                response.raise_for_status()
                assert not any(
                    r["pipeline_id"].startswith(("graphato-", "nikicas-hub-")) for r in response.json()
                )
        if json.loads(inner("inspect", "jenkins-parity", "--format", "{{json .State.Running}}")):
            jobs = json.loads(jenkins_api("/api/json?tree=jobs[name,lastBuild[building]]")["text"])
            assert not any(
                j["name"].startswith(("graphato-", "nikicas-hub-")) and j.get("lastBuild", {}).get("building")
                for j in jobs["jobs"]
            )
        backup = FOLDER / (
            "tunnel-before-renewal-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json"
        )
        backup.write_text(json.dumps(previous) + "\n")
        KEEP.unlink(missing_ok=True)
        for _ in range(30):
            if not alive(previous["pid"]) and not alive(previous.get("supervisor_pid", 0)):
                break
            time.sleep(1)
    assert not alive(previous["pid"]), "Existing tunnel process must not be duplicated"
    assert not previous.get("supervisor_pid") or not alive(previous["supervisor_pid"])
    if not args.renew:
        backup = FOLDER / "tunnel-before-supervision.json"
        assert not backup.exists(), "No implicit repeated restoration"
        backup.write_text(json.dumps(previous) + "\n")
    KEEP.write_text("Only the owned NAS test-VM connection; remove this file to stop supervision.\n")
    generation = uuid.uuid4().hex
    with (FOLDER / "tunnel-supervisor.log").open("ab") as log:
        supervisor = subprocess.Popen(
            [sys.executable, __file__, "--supervise", "--hours", str(args.hours), "--generation", generation],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    for _ in range(30):
        time.sleep(0.5)
        assert supervisor.poll() is None, "Tunnel supervisor exited"
        current = json.loads(STATE.read_text())
        # Windows venv launchers may delegate to another Python PID. The private
        # generation identifies this launch without assuming PID equality.
        if current.get("generation") == generation and current["connected_process_alive"]:
            break
    assert current.get("generation") == generation and current["connected_process_alive"]
    print(json.dumps(current))


if __name__ == "__main__":
    main()

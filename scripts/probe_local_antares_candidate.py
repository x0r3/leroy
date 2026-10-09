"""Contrast the NAS browser findings with a disposable local Linux execution."""

import argparse
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIN = "leroy-test-docker-1"


def inner(*args):
    return subprocess.check_output(["docker", "exec", DIN, "docker", *args], text=True, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt", required=True)
    parser.add_argument("--candidate", help="Optional exact commit for an unchanged-source control")
    parser.add_argument("--memory", choices=["3g", "4g"], default="3g")
    parser.add_argument("--test-file", action="append", default=[])
    parser.add_argument("--project", action="append", default=[])
    args = parser.parse_args()
    assert re.fullmatch(r"[a-z0-9-]{1,20}", args.attempt)
    assert all(re.fullmatch(r"tests/e2e/[a-z0-9-]+\.spec\.ts", value) for value in args.test_file)
    assert all(
        value
        in {
            "game-chromium",
            "game-mobile",
            "game-firefox",
            "game-webkit",
            "admin-chromium",
            "admin-surface-low-dpr",
            "admin-surface-firefox",
            "admin-surface-webkit",
        }
        for value in args.project
    )
    checkout = ROOT / ".sources/antares-nas-validation"
    commit = (
        args.candidate
        or subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
    )
    assert re.fullmatch(r"[a-f0-9]{40}", commit)
    assert not subprocess.check_output(["git", "-C", str(checkout), "status", "--porcelain"]).strip()
    outer = json.loads(subprocess.check_output(["docker", "inspect", DIN]))[0]
    assert outer["Config"]["Labels"]["com.docker.compose.project"] == "leroy-test"
    available = subprocess.check_output(
        ["docker", "exec", DIN, "cat", "/proc/meminfo"], text=True
    )
    available_kib = int(re.search(r"^MemAvailable:\s+(\d+) kB", available, re.MULTILINE)[1])
    required_kib = (int(args.memory[0]) + 1) * 1024**2
    assert available_kib >= required_kib, "Wait for adequate local Linux memory before another browser run"
    folder = ROOT / "test-results/nas-parity/followup/candidates/antares" / commit
    folder.mkdir(exist_ok=True)
    marker = folder / ("local-linux-browsers-" + args.attempt + ".json")
    assert not marker.exists(), "No implicit repeat"
    name = "leroy-antares-contrast-" + commit[:12] + "-" + args.attempt
    volume, database = name + "-work", name + "-db"
    assert name not in inner("ps", "-a", "--format", "{{.Names}}").splitlines()
    assert volume not in inner("volume", "ls", "--format", "{{.Name}}").splitlines()
    image = "mcr.microsoft.com/playwright:v1.61.1-noble"
    image_id = inner("image", "inspect", image, "--format", "{{.Id}}").strip()
    inputs = ROOT / ".sources/antares-nas-bundles"
    inputs.mkdir(exist_ok=True)
    archive = inputs / (commit + ".tar")
    subprocess.run(
        ["git", "-C", str(checkout), "archive", "--format=tar", "--output", str(archive), commit], check=True
    )
    remote_archive = "/sources/antares-nas-bundles/" + archive.name
    subprocess.run(["docker", "exec", DIN, "test", "-f", remote_archive], check=True)
    inner("volume", "create", "--label", "io.leroy.antares-contrast=true", volume)
    inner(
        "run",
        "-d",
        "--name",
        database,
        "--label",
        "io.leroy.antares-contrast=true",
        "--network",
        "leroy-jobs",
        "--memory",
        "512m",
        "--cpus",
        "1",
        "-e",
        "POSTGRES_DB=antares_test",
        "-e",
        "POSTGRES_USER=antares",
        "-e",
        "POSTGRES_PASSWORD=antares-test-password",
        "postgres:18.4-alpine3.24",
    )
    try:
        for _ in range(60):
            try:
                inner("exec", database, "pg_isready", "-U", "antares", "-d", "antares_test")
                break
            except subprocess.CalledProcessError:
                time.sleep(1)
        else:
            raise TimeoutError("Owned contrast database did not start")
        program = """set -eu
mkdir /work/repo
tar -xf /input/source.tar -C /work/repo
cd /work/repo
npm ci --no-audit --no-fund
npm run build:server
npm run build:game
npm run build:admin
node --import tsx --input-type=module -e "import {resetAndInstallTestDatabase} from './tests/integration/helpers/test-database.ts'; await resetAndInstallTestDatabase();"
"""
        program += (
            "node node_modules/playwright/cli.js test "
            + " ".join([*args.test_file, *("--project=" + project for project in args.project)])
            + "\n"
        )
        command = [
            "docker",
            "exec",
            DIN,
            "docker",
            "run",
            "--name",
            name,
            "--label",
            "io.leroy.antares-contrast=true",
            "--init",
            "--ipc=host",
            "--network",
            "leroy-jobs",
            "--memory",
            args.memory,
            "--cpus",
            "6",
            "-v",
            volume + ":/work",
            "--mount",
            "type=bind,src=" + remote_archive + ",dst=/input/source.tar,readonly",
            "--user",
            "0:0",
            "-e",
            "HOME=/tmp",
            "-e",
            "CI=true",
            "-e",
            "PLAYWRIGHT_BROWSERS_PATH=/ms-playwright",
            "-e",
            "NODE_OPTIONS=--max-old-space-size=2048",
            "-e",
            "TEST_DATABASE_URL=postgres://antares:antares-test-password@" + database + ":5432/antares_test",
            image,
            "sh",
            "-c",
            program,
        ]
        started = time.monotonic()
        started_wall = int(time.time())
        print("Local Linux contrast:", commit, flush=True)
        with marker.with_suffix(".log").open("w", encoding="utf-8") as log:
            try:
                result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=2700)
                code, timed_out = result.returncode, False
            except subprocess.TimeoutExpired:
                code, timed_out = None, True
        container = json.loads(inner("inspect", name))[0]
        resource_events = [
            json.loads(line)
            for line in inner(
                "events",
                "--since",
                str(started_wall),
                "--until",
                str(int(time.time())),
                "--filter",
                "type=container",
                "--filter",
                "container=" + container["Id"],
                "--filter",
                "event=oom",
                "--format",
                "{{json .}}",
            ).splitlines()
            if line.strip()
        ]
        report = {
            "commit": commit,
            "image": image,
            "image_id": image_id,
            "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "returncode": code,
            "timed_out": timed_out,
            "passed": code == 0,
            "duration_seconds": time.monotonic() - started,
            "diagnostic_only": True,
            "nas_acceptance": False,
            "memory_limit": args.memory,
            "initial_host_available_kib": available_kib,
            "cpu_limit": 6,
            "workspace_volume": volume,
            "test_files": args.test_file,
            "projects": args.project,
            "full_matrix_requested": not args.test_file and not args.project,
            "container_state": container["State"],
            "oom_events": resource_events,
        }
        marker.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report), flush=True)
    finally:
        for target in [name, database]:
            result = subprocess.run(["docker", "exec", DIN, "docker", "inspect", target], capture_output=True)
            if result.returncode == 0:
                info = json.loads(result.stdout)[0]
                assert info["Config"]["Labels"]["io.leroy.antares-contrast"] == "true"
                inner("rm", "-f", "-v", target)
    print("Workspace retained for evidence:", volume, flush=True)


if __name__ == "__main__":
    main()

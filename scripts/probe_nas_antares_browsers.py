"""Run the unchanged browser matrix diagnostically after an earlier gate failed.

The existing owned Jenkins workspace is checked against the candidate commit.
A fresh disposable database is used; this never counts as a full CI run.
"""

import argparse
import json
import re
import shlex
import subprocess
import time
from datetime import datetime, timezone

from nas_followup_support import (
    inner,
    production_build,
    production_jobs,
    remote,
    wait_production_build,
    wait_production_jobs,
)
from nas_gitea_target import idle
from nas_ssh import ROOT, run_script


def resource_snapshot():
    """Read only the owned daemon's pressure counters and host load indicators."""
    program = r"""
import json,pathlib,subprocess
assert pathlib.Path('/volume1/docker/leroy-nas-parity/.leroy-owned').is_file()
outer=json.loads(subprocess.check_output(['docker','inspect','leroy-nas-parity-docker-1'],text=True,timeout=20))[0]
assert outer['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity'
root=pathlib.Path('/sys/fs/cgroup/system.slice/docker-'+outer['Id']+'.scope')
fields=['cpu.stat','cpu.pressure','memory.current','memory.events','memory.swap.current','memory.pressure','io.pressure','io.stat']
print(json.dumps({'owned_daemon_id':outer['Id'],
 'cgroup':{name:(root/name).read_text().strip() for name in fields if (root/name).is_file()},
 'host_pressure':{name:pathlib.Path('/proc/pressure/'+name).read_text().strip() for name in ['cpu','memory','io']},
 'host_mem_available':next(line for line in pathlib.Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))}))
"""
    response = run_script("python3 - <<'PY'\n" + program + "\nPY\n",
                          ROOT / ".local/nas-ssh.json", sudo=True, timeout=40)
    assert response.returncode == 0, response.stderr[-1500:]
    return json.loads(response.stdout)


def wait_helpers_removed(names, timeout=30):
    """Docker stop can return before asynchronous --rm removal completes."""
    deadline = time.monotonic() + timeout
    while True:
        remaining = set(inner("ps", "-a", "--format", "{{.Names}}").splitlines())
        if not names & remaining:
            return
        if time.monotonic() >= deadline:
            raise TimeoutError("Diagnostic helpers were not completely removed")
        time.sleep(min(1, max(0, deadline - time.monotonic())))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate")
    parser.add_argument(
        "--prepare",
        action="store_true",
        help="Check out the staged candidate and rebuild assets before this diagnostic",
    )
    parser.add_argument(
        "--attempt", required=True, help="Distinct named diagnostic; previous attempts are retained"
    )
    parser.add_argument("--test-file", action="append", default=[], help="Optional focused E2E file")
    parser.add_argument("--project", action="append", default=[], help="Optional Playwright project")
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    parser.add_argument("--database-tmpfs", action="store_true",
                        help="Diagnostic only: put this disposable PostgreSQL database in bounded RAM")
    parser.add_argument("--database-tmpfs-size", choices=["512m", "1g"], default="512m",
                        help="Bounded disposable data/WAL capacity; full snapshot tests exceed 512 MiB")
    parser.add_argument("--browser-tmpfs", action="store_true",
                        help="Diagnostic only: put disposable browser profiles and temporary files in bounded RAM")
    parser.add_argument("--artifacts-in-tmpfs", action="store_true",
                        help="Diagnostic only: write traces/video in browser tmpfs, then preserve them after tests")
    args = parser.parse_args()
    assert args.database_tmpfs or args.database_tmpfs_size == "512m"
    assert not args.artifacts_in_tmpfs or args.browser_tmpfs, "RAM artifacts require the bounded browser tmpfs"
    assert re.fullmatch(r"[a-z0-9-]{1,24}", args.attempt)
    assert 60 <= args.timeout_seconds <= 3600
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
    commit = (
        args.candidate
        or subprocess.check_output(
            ["git", "-C", str(ROOT / ".sources/antares-nas-validation"), "rev-parse", "HEAD"], text=True
        ).strip()
    )
    assert re.fullmatch(r"[a-f0-9]{40}", commit)
    folder = ROOT / "test-results/nas-parity/followup/candidates/antares" / commit
    marker = folder / ("focused-browsers-" + args.attempt + ".json")
    assert not marker.exists(), "No implicit diagnostic rerun"
    production_jobs_before = wait_production_jobs()
    production_before = wait_production_build()
    idle()
    assert json.loads(inner("inspect", "jenkins-parity", "--format", "{{json .State.Running}}")) is False
    name = "antares-browser-probe-" + commit[:12] + "-" + args.attempt
    database = name + "-db"
    running = inner("ps", "--format", "{{.Names}}").splitlines()
    assert not any(item.startswith("antares-") for item in running), "Finish the other Antares probe"
    existing = set(inner("ps", "-a", "--format", "{{.Names}}").splitlines())
    assert not {name, database} & existing, "Do not reuse existing diagnostic containers"
    if args.prepare:
        staged = json.loads((folder / "staged.json").read_text())
        image = inner("inspect", "jenkins-parity", "--format", "{{.Image}}").strip()
        cpus = str(
            int(inner("inspect", "jenkins-parity", "--format", "{{.HostConfig.NanoCpus}}").strip())
            / 1_000_000_000
        )
        preparation = (
            "COMMIT="
            + repr(commit)
            + "\nSOURCE="
            + repr(staged["source"])
            + "\n"
            + r"""
import json,pathlib,subprocess
root=pathlib.Path('/var/jenkins_home/workspace/antares-ci')
assert not subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True).strip()
lock=(root/'package-lock.json').read_bytes()
subprocess.run(['git','fetch',SOURCE,COMMIT],cwd=root,check=True,capture_output=True)
subprocess.run(['git','checkout','--detach',COMMIT],cwd=root,check=True,capture_output=True)
assert lock==(root/'package-lock.json').read_bytes(), 'Dependency changes require a clean npm ci'
reports=[]
for task in ['lint','typecheck','build']:
 result=subprocess.run(['npm','run',task],cwd=root,text=True,capture_output=True,timeout=600)
 reports.append({'task':task,'returncode':result.returncode,'console':result.stdout+result.stderr})
 if result.returncode:break
print(json.dumps(reports))
"""
        )
        reports = json.loads(
            inner(
                "run",
                "--rm",
                "--name",
                name + "-prepare",
                "--label",
                "io.leroy.nas-parity=true",
                "--network",
                "leroy-jobs",
                "--volumes-from",
                "jenkins-parity",
                "--memory",
                "3g",
                "--cpus",
                cpus,
                "-e",
                "NODE_OPTIONS=--max-old-space-size=2048",
                "--entrypoint",
                "python3",
                image,
                "-c",
                preparation,
                timeout=1900,
            )
        )
        (folder / ("focused-browsers-" + args.attempt + "-preparation.json")).write_text(
            json.dumps(reports, indent=2) + "\n"
        )
        assert len(reports) == 3 and all(row["returncode"] == 0 for row in reports), (
            "Inspect the preparation logs"
        )
    inner(
        "run",
        "-d",
        "--rm",
        "--name",
        database,
        "--label",
        "io.leroy.nas-parity=true",
        "--network",
        "leroy-jobs",
        *(["--tmpfs", "/var/lib/postgresql:rw,nosuid,nodev,size=" + args.database_tmpfs_size] if args.database_tmpfs else []),
        "-e",
        "POSTGRES_DB=antares_test",
        "-e",
        "POSTGRES_USER=antares",
        "-e",
        "POSTGRES_PASSWORD=antares-test-password",
        "postgres:18.4-alpine3.24",
    )
    try:
        for _ in range(30):
            try:
                inner("exec", database, "pg_isready", "-h", "127.0.0.1", "-U", "antares", "-d", "antares_test")
                break
            except RuntimeError:
                time.sleep(2)
        else:
            raise TimeoutError("Browser probe database did not become ready")
        database_info = json.loads(inner("inspect", database))[0]
        durability = inner("exec", database, "psql", "-X", "-qAt", "-U", "antares", "-d", "antares_test",
                           "-c", "SELECT name,setting FROM pg_settings WHERE name IN ('fsync','synchronous_commit','full_page_writes') ORDER BY name")
        assert durability.strip().splitlines() == ["fsync|on", "full_page_writes|on", "synchronous_commit|on"]
        if args.database_tmpfs:
            assert database_info["HostConfig"]["Tmpfs"] == {
                "/var/lib/postgresql": "rw,nosuid,nodev,size=" + args.database_tmpfs_size,
            }
            assert not [m for m in database_info["Mounts"] if m["Type"] == "volume"]
        setup = "import {resetAndInstallTestDatabase} from './tests/integration/helpers/test-database.ts'; await resetAndInstallTestDatabase();"
        artifact_directory = "playwright-" + args.attempt if args.artifacts_in_tmpfs else "playwright"
        browser_command = shlex.join([
            "node", "node_modules/playwright/cli.js", "test", *args.test_file,
            *("--project=" + project for project in args.project),
            *(["--output=/tmp/leroy-playwright"] if args.artifacts_in_tmpfs else []),
        ])
        if args.artifacts_in_tmpfs:
            destination = "test-results/" + artifact_directory
            browser_command = (
                "test ! -e " + shlex.quote(destination) + " || exit 86; status=0; "
                + browser_command + " || status=$?; "
                + "if test -d /tmp/leroy-playwright; then mkdir -p test-results && cp -a /tmp/leroy-playwright "
                + shlex.quote(destination) + " || exit 87; fi; exit \"$status\""
            )
        command = [
            "run",
            "--name",
            name,
            "--label",
            "io.leroy.nas-parity=true",
            "--init",
            "--ipc=host",
            *(["--tmpfs", "/tmp:rw,nosuid,nodev,size=1g"] if args.browser_tmpfs else []),
            "--network",
            "leroy-jobs",
            "--volumes-from",
            "jenkins-parity",
            "--user",
            "0:0",
            "-e",
            "HOME=/tmp",
            "-e",
            "CI=true",
            "-e",
            "PLAYWRIGHT_BROWSERS_PATH=/ms-playwright",
            "-e",
            "TEST_DATABASE_URL=postgres://antares:antares-test-password@" + database + ":5432/antares_test",
            "--workdir",
            "/var/jenkins_home/workspace/antares-ci",
            "mcr.microsoft.com/playwright:v1.61.1-noble",
            "sh",
            "-c",
            'test "$(git rev-parse HEAD)" = "'
            + commit
            + '" && git diff --quiet && git diff --cached --quiet && '
            + shlex.join(["node", "--import", "tsx", "--input-type=module", "-e", setup])
            + " && "
            + "( " + browser_command + " )",
        ]
        program = (
            "ARGS="
            + repr(command)
            + "\nLIMIT="
            + repr(args.timeout_seconds)
            + "\n"
            + """
import json,pathlib,subprocess,time
assert pathlib.Path('/volume1/docker/leroy-nas-parity/.leroy-owned').is_file()
started=time.monotonic()
try:
 result=subprocess.run(['docker','exec','leroy-nas-parity-docker-1','docker',*ARGS],text=True,capture_output=True,timeout=LIMIT)
 report={'returncode':result.returncode,'console':result.stdout+result.stderr,'timed_out':False}
except subprocess.TimeoutExpired as error:
 report={'returncode':None,'console':(error.stdout or b'').decode(errors='replace')+(error.stderr or b'').decode(errors='replace'),'timed_out':True}
report['duration_seconds']=time.monotonic()-started
print(json.dumps(report))
"""
        )
        print("Antares browser diagnostic:", commit, flush=True)
        resources_before = resource_snapshot()
        started_at = datetime.now(timezone.utc).isoformat()
        result = json.loads(remote(program, timeout=args.timeout_seconds + 60))
        completed_at = datetime.now(timezone.utc).isoformat()
        marker.with_suffix(".log").write_text(result.pop("console"), encoding="utf-8")
        result.update(
            commit=commit,
            attempt=args.attempt,
            schema_installed_before_server=True,
            diagnostic_only=True,
            test_files=args.test_file,
            projects=args.project,
            diagnostic_timeout_seconds=args.timeout_seconds,
            full_matrix_requested=not args.test_file and not args.project,
            passed=result["returncode"] == 0,
            database_tmpfs=args.database_tmpfs,
            database_storage=database_info["HostConfig"].get("Tmpfs", {}),
            database_durability=durability.strip().splitlines(),
            browser_tmpfs=args.browser_tmpfs,
            artifacts_in_tmpfs=args.artifacts_in_tmpfs,
            artifact_directory=artifact_directory,
            started_at=started_at,
            completed_at=completed_at,
            production_before=production_before,
            production_jobs_before=production_jobs_before,
            resources_before=resources_before,
        )
        try:
            result["resources_after"] = resource_snapshot()
        except (RuntimeError, AssertionError, subprocess.SubprocessError, ValueError) as error:
            result["resources_after_error"] = type(error).__name__
        try:
            result["production_after"] = production_build()
            result["production_jobs_after"] = production_jobs()
            result["production_jobs_unchanged"] = (
                result["production_jobs_after"]["jobs"] == production_jobs_before["jobs"]
                and not any(row["building"] for row in result["production_jobs_after"]["jobs"].values())
            )
            result["production_build_unchanged"] = (
                result["production_after"]["number"] == production_before["number"]
                and not result["production_after"]["building"]
                and result["production_jobs_unchanged"]
            )
        except (RuntimeError, subprocess.SubprocessError, ValueError) as error:
            result["production_after_error"] = type(error).__name__
            result["production_build_unchanged"] = False
        marker.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps({key: result[key] for key in (
            "commit", "attempt", "passed", "timed_out", "duration_seconds",
            "full_matrix_requested", "database_tmpfs", "browser_tmpfs",
            "artifacts_in_tmpfs", "production_build_unchanged",
        )}), flush=True)
    finally:
        try:
            inner("rm", "-f", "-v", name, timeout=90)
        finally:
            inner("stop", database, timeout=90)
    wait_helpers_removed({name, database})
    result["helpers_removed"] = True
    marker.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()

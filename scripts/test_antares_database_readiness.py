"""Expose PostgreSQL's temporary init server with a real local Docker fixture."""

import argparse
import json
import re
import tempfile
import time
import uuid
from pathlib import Path

from nas_ssh import ROOT
from test_antares_database_cleanup import docker

from leroy.actions import antares_database


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt", required=True)
    parser.add_argument("--expect-premature", action="store_true")
    args = parser.parse_args()
    assert re.fullmatch(r"[a-z0-9-]{1,32}", args.attempt)
    assert docker("info", "--format", "{{.Name}}").stdout.strip() == "docker-desktop"
    folder = ROOT / "test-results/nas-parity/followup/antares-database-readiness"
    folder.mkdir(exist_ok=True)
    output = folder / (args.attempt + ".json")
    assert not output.exists(), "Preserve previous evidence"
    run_id = uuid.uuid4().hex
    image = "leroy-postgres-readiness:" + run_id
    name = "leroy-antares-" + run_id
    try:
        with tempfile.TemporaryDirectory(prefix="leroy-postgres-readiness-") as directory:
            root = Path(directory)
            (root / "Dockerfile").write_text("FROM postgres:18.4-alpine3.24\nCOPY init.sql /docker-entrypoint-initdb.d/99-readiness.sql\n")
            (root / "init.sql").write_text("SELECT pg_sleep(8);\n")
            docker("build", "--network=none", "--pull=false", "-t", image, str(root))
        started = time.monotonic()
        context = {"run": {"id": run_id}, "profile": {"network": "bridge", "postgres_image": image}}
        antares_database(context)
        probe = docker("exec", name, "pg_isready", "-h", "127.0.0.1", "-U", "antares", "-d", "antares_test", check=False)
        logs = docker("logs", name)
        (folder / (args.attempt + ".log")).write_text(logs.stdout + logs.stderr)
        report = {"run": run_id, "local_only": True, "initialization_delay_seconds": 8,
                  "action_seconds": time.monotonic() - started, "tcp_ready_after_action": probe.returncode == 0,
                  "original_premature_readiness_reproduced": probe.returncode != 0}
        output.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report))
        assert (probe.returncode != 0) == args.expect_premature
    finally:
        current = docker("inspect", name, check=False)
        if current.returncode == 0:
            assert json.loads(current.stdout)[0]["Config"]["Labels"]["io.leroy.run"] == run_id
            docker("rm", "-f", "-v", name)
        if docker("image", "inspect", image, check=False).returncode == 0:
            docker("image", "rm", image)


if __name__ == "__main__":
    main()

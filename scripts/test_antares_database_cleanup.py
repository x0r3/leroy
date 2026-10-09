"""Check actual PostgreSQL volume cleanup on the local Docker Desktop daemon."""

import argparse
import json
import os
import re
import subprocess
import uuid
from datetime import datetime, timezone

from nas_ssh import ROOT

from leroy.actions import antares_database, cleanup


def docker(*args, check=True):
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=check)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--expect-retained", action="store_true")
    args = parser.parse_args()
    assert re.fullmatch("[a-z0-9-]{1,32}", args.label)
    assert docker("info", "--format", "{{.Name}}").stdout.strip() == "docker-desktop", "Local Docker Desktop only"
    folder = ROOT / "test-results/nas-parity/followup/antares-database-cleanup"
    folder.mkdir(exist_ok=True)
    target = folder / (args.label + ".json")
    assert not target.exists(), "Retain previous evidence"
    run_id = uuid.uuid4().hex
    name = "leroy-antares-" + run_id
    context = {"run": {"id": run_id}, "profile": {"network": "bridge"}, "values": {}}
    volumes = []
    keeper = "leroy-cleanup-keeper-" + run_id
    named_volume = "leroy-cleanup-named-" + run_id
    os.environ["HOSTNAME"] = "local-cleanup-check-worker"
    try:
        context["values"] = antares_database(context)
        info = json.loads(docker("inspect", name).stdout)[0]
        assert info["Config"]["Labels"]["io.leroy.run"] == run_id
        volumes = [mount["Name"] for mount in info["Mounts"] if mount["Type"] == "volume"]
        assert len(volumes) == 1 and re.fullmatch("[a-f0-9]{64}", volumes[0])
        result = docker("exec", name, "psql", "-X", "-qAt", "-U", "antares", "-d", "antares_test",
                        "-c", "CREATE TABLE cleanup_probe(value integer); INSERT INTO cleanup_probe VALUES (42); SELECT value FROM cleanup_probe")
        assert result.stdout.strip() == "42"
        docker("volume", "create", "--label", "io.leroy.cleanup-probe=" + run_id, named_volume)
        docker("run", "-d", "--name", keeper, "--label", "io.leroy.run=" + run_id,
               "--network", "none", "--memory", "64m", "--entrypoint", "sh",
               "--mount", "type=volume,source=" + named_volume + ",target=/var/lib/postgresql",
               "postgres:18.4-alpine3.24", "-c", "sleep 120")
        cleanup(context)
        assert docker("inspect", name, check=False).returncode != 0
        assert docker("inspect", keeper, check=False).returncode != 0
        assert docker("volume", "inspect", named_volume, check=False).returncode == 0
        retained = [volume for volume in volumes if docker("volume", "inspect", volume, check=False).returncode == 0]
        report = {
            "at": datetime.now(timezone.utc).isoformat(), "local_only": True,
            "run": run_id, "database_write_verified": True, "container_removed": True,
            "auto_remove": info["HostConfig"]["AutoRemove"], "retained_volumes": retained,
            "named_volume_preserved": True,
            "cleanup_passed": not retained, "original_leak_reproduced": bool(retained),
        }
        target.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report), flush=True)
        assert bool(retained) == args.expect_retained
    finally:
        current = docker("inspect", keeper, check=False)
        if current.returncode == 0:
            assert json.loads(current.stdout)[0]["Config"]["Labels"]["io.leroy.run"] == run_id
            docker("rm", "-f", "-v", keeper)
        current = docker("volume", "inspect", named_volume, check=False)
        if current.returncode == 0:
            assert json.loads(current.stdout)[0]["Labels"]["io.leroy.cleanup-probe"] == run_id
            docker("volume", "rm", named_volume)
        current = docker("inspect", name, check=False)
        if current.returncode == 0:
            info = json.loads(current.stdout)[0]
            assert info["Config"]["Labels"]["io.leroy.run"] == run_id
            docker("rm", "-f", "-v", name)
        for volume in volumes:
            if docker("volume", "inspect", volume, check=False).returncode == 0:
                assert not docker("ps", "-aq", "--filter", "volume=" + volume).stdout.strip()
                docker("volume", "rm", volume)


if __name__ == "__main__":
    main()

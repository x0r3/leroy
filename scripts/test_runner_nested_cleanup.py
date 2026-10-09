"""Exercise actual local Docker recovery after a worker lost its nested helpers."""

import json
import uuid

from nas_ssh import ROOT
from test_antares_database_cleanup import docker

from leroy.runner import cleanup_finished_run


def main():
    assert docker("info", "--format", "{{.Name}}").stdout.strip() == "docker-desktop"
    folder = ROOT / "test-results/nas-parity/followup/runner-nested-cleanup"
    folder.mkdir(exist_ok=True)
    target = folder / "local.json"
    assert not target.exists()
    run_id, other_id = uuid.uuid4().hex, uuid.uuid4().hex
    worker = "leroy-" + run_id
    work, named = worker + "-work", worker + "-retained"
    child, other = worker + "-child", "leroy-unrelated-" + other_id
    volumes = []
    try:
        for name, owner, mount in [(worker, run_id, work), (child, run_id, named), (other, other_id, None)]:
            args = ["run", "-d", "--name", name, "--label", "io.leroy.run=" + owner,
                    "--network", "none", "--memory", "64m", "--entrypoint", "sh"]
            if mount:
                docker("volume", "create", "--label", "io.leroy.cleanup-probe=" + run_id, mount)
                args += ["--mount", "type=volume,source=" + mount + ",target=/work"]
            docker(*args, "postgres:18.4-alpine3.24", "-c", "sleep 180")
            info = json.loads(docker("inspect", name).stdout)[0]
            volumes += [m["Name"] for m in info["Mounts"] if m["Type"] == "volume" and m["Destination"] != "/work"]
        docker("kill", worker)
        cleanup_finished_run(run_id)
        assert docker("inspect", worker, check=False).returncode != 0
        assert docker("inspect", child, check=False).returncode != 0
        assert docker("volume", "inspect", work, check=False).returncode != 0
        assert docker("volume", "inspect", named, check=False).returncode == 0
        assert json.loads(docker("inspect", other).stdout)[0]["State"]["Running"]
        present = [v for v in volumes if docker("volume", "inspect", v, check=False).returncode == 0]
        assert len(present) == 1, "Only the unrelated container's anonymous volume remains"
        report = {"passed": True, "local_only": True, "run": run_id, "worker_removed": True,
                  "nested_helper_removed": True, "anonymous_volumes_removed": True,
                  "explicitly_named_helper_volume_preserved": True, "unrelated_container_preserved": True}
        target.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report))
    finally:
        for name in (worker, child, other):
            found = docker("inspect", name, check=False)
            if found.returncode == 0:
                assert json.loads(found.stdout)[0]["Config"]["Labels"]["io.leroy.run"] in (run_id, other_id)
                docker("rm", "-f", "-v", name)
        for volume in (work, named):
            found = docker("volume", "inspect", volume, check=False)
            if found.returncode == 0:
                assert json.loads(found.stdout)[0]["Labels"]["io.leroy.cleanup-probe"] == run_id
                docker("volume", "rm", volume)


if __name__ == "__main__":
    main()

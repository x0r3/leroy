"""Bounded two-slot NAS load test; restore the one-slot profile afterwards."""

import hashlib
import json
import time
from contextlib import closing

from compare_nas_antares import client
from nas_followup_support import inner, remote
from nas_graphato_resources import PROGRAM as PRESSURE
from nas_ssh import ROOT, upload_file
from test_nas_lifecycle import ACTIVE, finished

from leroy.schema import Pipeline, Step

FOLDER = ROOT / "test-results/nas-parity/followup/nas-parallel"
WORK = """
import hashlib,json,pathlib,resource,time
started=time.time()
memory=bytearray(256*1024*1024)
for offset in range(0,len(memory),4096):memory[offset]=123
checks=0
while time.time()-started<60:
 hashlib.sha256(memory).digest()
 checks+=1
 time.sleep(.1)
pathlib.Path('load.json').write_text(json.dumps({'started':started,'finished':time.time(),
 'allocated_bytes':len(memory),'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'hashes':checks}))
print('bounded load complete',checks,flush=True)
"""


def main():
    FOLDER.mkdir(parents=True, exist_ok=True)
    assert not (FOLDER / "state.json").exists(), "Inspect previous parallel test before retrying"
    original = ROOT / ".local/nas-parity/config/runner.toml"
    content = original.read_text()
    assert content.startswith("capacity = 1\n") and "[profiles.nas-capacity]" not in content
    backup = ROOT / ".local/nas-parity/runner-before-parallel.toml"
    backup.write_bytes(original.read_bytes())
    modified = (
        content.replace("capacity = 1\n", "capacity = 2\n", 1)
        + """
[profiles.nas-capacity]
image = "leroy-job:nas-parity"
network = "leroy-jobs"
memory = "512m"
memory_reservation = "128m"
cpus = 0.5
pids_limit = 128
docker = false
host_mappings = {controller = "10.232.98.10"}
"""
    )
    candidate = ROOT / ".local/nas-parity/runner-parallel.toml"
    candidate.write_text(modified)
    remote_path = "/volume1/docker/leroy-nas-parity/config/runner.toml"
    expected = hashlib.sha256(backup.read_bytes()).hexdigest()
    probe = (
        "import pathlib,hashlib\nprint(hashlib.sha256(pathlib.Path("
        + repr(remote_path)
        + ").read_bytes()).hexdigest())"
    )
    assert remote(probe).strip() == expected
    state = {"runs": [], "samples": [], "original_runner_sha256": expected}

    def save():
        (FOLDER / "state.json").write_text(json.dumps(state, indent=2) + "\n")

    def restart():
        remote(
            "import pathlib,subprocess\nassert pathlib.Path('/volume1/docker/leroy-nas-parity/.leroy-owned').is_file()\nsubprocess.run(['docker','restart','leroy-nas-parity-runner-1'],check=True,capture_output=True,timeout=90)\nprint('Owned runner restarted')",
            timeout=120,
        )

    with closing(client()) as api:
        for status in ACTIVE:
            assert not api.get("/api/runs", params={"status": status}).json()
        assert not any(p["enabled"] for p in api.get("/api/pipelines").json())
        assert json.loads(inner("inspect", "jenkins-parity", "--format", "{{json .State.Running}}")) is False
        save()
        try:
            upload_file(candidate, remote_path, ROOT / ".local/nas-ssh.json")
            restart()
            for _ in range(30):
                runners = api.get("/api/runners").json()
                if any(r["id"] == "runner-nas-parity" and r["capacity"] == 2 for r in runners):
                    break
                time.sleep(2)
            else:
                raise TimeoutError("Temporary runner capacity not visible")
            spec = Pipeline(
                id="leroy-nas-diagnostics",
                name="NAS-Abnahme: Parallelbetrieb",
                group="Abnahme",
                enabled=False,
                profile="nas-capacity",
                timeout=300,
                concurrency="parallel",
                source={"kind": "diagnostic", "scenario": "bounded parallel load"},
                steps=[
                    Step(
                        id="load",
                        name="256 MiB and bounded CPU",
                        timeout=180,
                        command=["python", "-c", WORK],
                        artifacts=["load.json"],
                    )
                ],
            )
            api.put("/api/pipelines/" + spec.id, json=spec.model_dump()).raise_for_status()
            for _ in range(3):
                response = api.post("/api/pipelines/" + spec.id + "/runs", json={})
                response.raise_for_status()
                state["runs"].append(response.json()["id"])
                save()
            deadline = time.monotonic() + 240
            overlap = False
            while time.monotonic() < deadline:
                started = time.monotonic()
                rows = [api.get("/api/runs/" + run_id).json() for run_id in state["runs"]]
                seconds = time.monotonic() - started
                running = [r for r in rows if r["status"] == "running"]
                queued = [r for r in rows if r["status"] == "queued"]
                workers = [r for r in running if any(s["status"] == "running" for s in r["steps"])]
                assert len(running) <= 2
                if len(workers) == 2 and len(queued) == 1:
                    overlap = True
                sample = {
                    "at": time.time(),
                    "api_seconds_three_requests": seconds,
                    "states": [r["status"] for r in rows],
                }
                sample["resources"] = json.loads(remote(PRESSURE, timeout=40))
                if workers:
                    fmt = "{{json .State}}"
                    observations = []
                    for row in workers:
                        # Only State is inspected: no credentials/attempt tokens.
                        try:
                            info = json.loads(inner("inspect", "leroy-" + row["id"], "--format", fmt))
                        except RuntimeError:
                            assert api.get("/api/runs/" + row["id"]).json()["status"] not in ACTIVE
                            continue
                        observations.append(
                            {"run": row["id"], "oom_killed": info["OOMKilled"], "running": info["Running"]}
                        )
                    sample["containers"] = observations
                state["samples"].append(sample)
                save()
                if all(r["status"] not in ACTIVE for r in rows):
                    break
                time.sleep(8)
            else:
                raise TimeoutError("Parallel load did not finish")
            assert overlap, "Two workers and a third queued job must be observed simultaneously"
            for name in ("oom", "oom_kill"):
                assert (
                    state["samples"][0]["resources"]["memory.events"][name]
                    == state["samples"][-1]["resources"]["memory.events"][name]
                )
            artifacts = []
            for row in rows:
                (FOLDER / (row["id"] + ".json")).write_text(json.dumps(row, indent=2) + "\n")
                assert row["status"] == "succeeded" and len(row["artifacts"]) == 1
                artifact = row["artifacts"][0]
                response = api.get("/api/artifacts/" + artifact["id"])
                response.raise_for_status()
                assert (
                    len(response.content) == artifact["size"]
                    and hashlib.sha256(response.content).hexdigest() == artifact["sha256"]
                )
                result = response.json()
                assert result["max_rss_kib"] > 256 * 1024 and result["hashes"] > 0
                artifacts.append(result)
            state.update(
                two_simultaneous_workers_and_third_queued=True, artifacts=artifacts, workload_passed=True
            )
            save()
        finally:
            for run_id in state["runs"]:
                row = api.get("/api/runs/" + run_id).json()
                if row["status"] in ACTIVE:
                    api.post("/api/runs/" + run_id + "/cancel", json={}).raise_for_status()
                    finished(api, run_id)
            upload_file(backup, remote_path, ROOT / ".local/nas-ssh.json")
            restart()
            assert remote(probe).strip() == expected
            # Retain the historic run snapshots but leave a runnable, ordinary
            # diagnostic definition after removing the temporary profile.
            response = api.get("/api/pipelines")
            spec = next(p["spec"] for p in response.json() if p["id"] == "leroy-nas-diagnostics")
            spec["profile"] = "graphato"
            api.put("/api/pipelines/" + spec["id"], json=spec).raise_for_status()
            state["original_capacity_and_profiles_restored"] = True
            save()
    print(json.dumps({k: v for k, v in state.items() if k != "samples"}), flush=True)


if __name__ == "__main__":
    main()

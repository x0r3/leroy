"""Verify real NAS timeout cleanup across the unchanged 90-second worker lease."""

import argparse
import json
import re
import time
from contextlib import closing
from datetime import datetime

from compare_nas_antares import client
from compare_nas_job import collect_artifacts
from nas_followup_support import inner
from nas_ssh import ROOT

from leroy.schema import Pipeline, Step

CLEANUP = r'''
import json,pathlib,subprocess,time
from leroy.actions import cleanup
context=json.loads(pathlib.Path('/work/cleanup-input.json').read_text())
name=context['values']['database_container']
def docker(*args):return subprocess.run(['docker',*args],text=True,capture_output=True)
info=docker('inspect',name);assert info.returncode==0
info=json.loads(info.stdout)[0]
volumes=[m['Name'] for m in info['Mounts'] if m['Type']=='volume']
assert len(volumes)==1 and len(volumes[0])==64
started=time.monotonic()
for tick in range(110):
 print('Cleanup remains active after cancellation:',tick,flush=True)
 time.sleep(1)
write=docker('exec',name,'psql','-X','-qAt','-U','antares','-d','antares_test','-c','CREATE TABLE cleanup_probe(value integer); INSERT INTO cleanup_probe VALUES (42); SELECT value FROM cleanup_probe')
assert write.returncode==0 and write.stdout.strip()=='42', write.stderr
cleanup(context)
assert docker('inspect',name).returncode!=0
assert all(docker('volume','inspect',volume).returncode!=0 for volume in volumes)
pathlib.Path('cleanup-proof.json').write_text(json.dumps({'database_write_verified':True,'container_removed':True,'anonymous_volumes_removed':True,'delay_seconds':time.monotonic()-started,'volumes':volumes}))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt", default="cancel-cleanup-runtime")
    parser.add_argument("--deployment", choices=["cancel-cleanup", "postgres-readiness"], default="cancel-cleanup")
    args = parser.parse_args()
    assert re.fullmatch(r"cancel-cleanup-[a-z0-9-]{1,32}", args.attempt)
    folder = ROOT / "test-results/nas-parity/followup" / args.attempt
    folder.mkdir(exist_ok=True)
    marker = folder / "run-id.json"
    deployment = json.loads((folder.parent / (args.deployment + "-deployment.json")).read_text())
    with closing(client()) as api:
        if marker.exists():
            run_id = json.loads(marker.read_text())["id"]
        else:
            for status in ("running", "waiting", "queued"):
                response = api.get("/api/runs", params={"status": status})
                response.raise_for_status()
                assert not response.json()
            assert not any(p["enabled"] for p in api.get("/api/pipelines").json())
            assert json.loads(inner("inspect", "jenkins-parity", "--format", "{{json .State.Running}}")) is False
            spec = Pipeline(
                id="leroy-nas-diagnostics", name="NAS-Abnahme: Aufräumen nach Zeitlimit", group="Abnahme",
                profile="antares", enabled=False, timeout=180,
                source={"kind": "diagnostic", "scenario": "cancel-cleanup-runtime"},
                steps=[
                    Step(id="postgres", name="Temporäre Datenbank", action="antares_database"),
                    Step(id="work", name="Arbeit bis zum Zeitlimit", needs=["postgres"],
                         command=["python", "-c", "import time; print('Work ready',flush=True); time.sleep(300)"], timeout=360),
                    Step(id="cleanup", name="Aufräumen länger als eine Lease", needs=["work"], always=True,
                         command=["python", "-c", CLEANUP], timeout=300, artifacts=["cleanup-proof.json"]),
                ],
            )
            (folder / "definition.json").write_text(spec.model_dump_json(indent=2))
            api.put("/api/pipelines/" + spec.id, json=spec.model_dump()).raise_for_status()
            response = api.post("/api/pipelines/" + spec.id + "/runs", json={})
            response.raise_for_status()
            run_id = response.json()["id"]
            marker.write_text(json.dumps({"id": run_id}) + "\n")
        print("NAS timeout cleanup:", run_id, flush=True)
        observations = []
        deadline = time.monotonic() + 480
        previous = None
        while time.monotonic() < deadline:
            response = api.get("/api/runs/" + run_id)
            response.raise_for_status()
            run = response.json()
            state = {k: run[k] for k in ("status", "cancel_requested", "lease_until", "reason")}
            observations.append(state)
            stages = [(step["id"], step["status"]) for step in run["steps"]]
            if (run["status"], stages) != previous:
                print(run["status"], stages, flush=True)
                previous = (run["status"], stages)
            if run["status"] not in ("running", "waiting", "queued"):
                break
            time.sleep(3)
        else:
            raise TimeoutError(run_id)
        (folder / "run.json").write_text(json.dumps(run, indent=2) + "\n")
        (folder / "lease-observations.json").write_text(json.dumps(observations, indent=2) + "\n")
        collect_artifacts(api, run, folder)
        for step in run["steps"]:
            response = api.get(f"/api/runs/{run_id}/logs/{step['id']}")
            response.raise_for_status()
            (folder / (step["id"] + ".log")).write_text(response.json()["text"], encoding="utf-8")
        assert run["status"] == "timed_out", run["reason"]
        assert next(s for s in run["steps"] if s["id"] == "cleanup")["status"] == "succeeded"
        proof = json.loads((folder / "leroy-artifacts/cleanup/cleanup-proof.json").read_text())
        assert proof["delay_seconds"] >= 110 and proof["anonymous_volumes_removed"]
        leases = [datetime.fromisoformat(o["lease_until"]) for o in observations
                  if o["cancel_requested"] and o["lease_until"]]
        assert (max(leases) - min(leases)).total_seconds() >= 90
        expected_image = deployment["images"]["leroy-job:nas-parity"]["after"]
        assert run["image_digest"] == expected_image
        report = {"passed": True, "run": run_id, "final_status": run["status"],
                  "lease_renewed_during_cleanup_seconds": (max(leases) - min(leases)).total_seconds(),
                  "proof": proof, "image": expected_image, "lease_seconds_unchanged": 90,
                  "production_modified": False}
        (folder / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()

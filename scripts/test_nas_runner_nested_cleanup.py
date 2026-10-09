"""Kill one explicit NAS diagnostic worker and verify its helpers are reaped."""

import json
import time
from contextlib import closing

from compare_nas_antares import client
from nas_followup_support import inner
from nas_ssh import ROOT

from leroy.schema import Pipeline, Step

PROGRAM = r'''
import json,pathlib,subprocess,time
run_id=json.loads(pathlib.Path('/work/work-input.json').read_text())['run']['id']
name='leroy-orphan-probe-'+run_id
subprocess.run(['docker','run','-d','--name',name,'--label','io.leroy.run='+run_id,'--network','none','--memory','64m','--entrypoint','sh','postgres:18.4-alpine3.24','-c','sleep 600'],check=True)
print('HELPER_READY '+name,flush=True)
time.sleep(600)
'''


def main():
    folder = ROOT / "test-results/nas-parity/followup/runner-nested-cleanup"
    deployment = json.loads((folder / "deployment.json").read_text())
    marker = folder / "nas-run-id.json"
    assert not marker.exists(), "Do not repeat an injected crash implicitly"
    with closing(client()) as api:
        for status in ("running", "waiting", "queued"):
            response = api.get("/api/runs", params={"status": status})
            response.raise_for_status()
            assert not response.json()
        assert not any(p["enabled"] for p in api.get("/api/pipelines").json())
        assert json.loads(inner("inspect", "jenkins-parity", "--format", "{{json .State.Running}}")) is False
        spec = Pipeline(id="leroy-nas-diagnostics", name="NAS-Abnahme: Worker-Ausfall mit Hilfscontainer",
                        group="Abnahme", profile="antares", enabled=False, timeout=600,
                        source={"kind": "diagnostic", "scenario": "nested-helper-recovery"},
                        steps=[Step(id="work", name="Worker mit temporärem Hilfscontainer", command=["python", "-c", PROGRAM], timeout=600)])
        (folder / "definition.json").write_text(spec.model_dump_json(indent=2))
        api.put("/api/pipelines/" + spec.id, json=spec.model_dump()).raise_for_status()
        response = api.post("/api/pipelines/" + spec.id + "/runs", json={})
        response.raise_for_status()
        run_id = response.json()["id"]
        marker.write_text(json.dumps({"id": run_id}) + "\n")
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            response = api.get(f"/api/runs/{run_id}/logs/work")
            response.raise_for_status()
            if "HELPER_READY " in response.json()["text"]:
                break
            time.sleep(2)
        else:
            raise TimeoutError("Helper did not start: " + run_id)
        worker, helper = "leroy-" + run_id, "leroy-orphan-probe-" + run_id
        owner = json.loads(inner("inspect", worker))[0]
        child = json.loads(inner("inspect", helper))[0]
        assert owner["Config"]["Labels"]["io.leroy.run"] == run_id
        assert owner["Config"]["Labels"]["io.leroy.runner"] == "runner-nas-parity"
        assert child["Config"]["Labels"]["io.leroy.run"] == run_id
        volumes = [mount["Name"] for mount in child["Mounts"] if mount["Type"] == "volume"]
        assert len(volumes) == 1 and len(volumes[0]) == 64
        inner("kill", owner["Id"])
        print("Injected diagnostic worker crash:", run_id, flush=True)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            response = api.get("/api/runs/" + run_id)
            response.raise_for_status()
            run = response.json()
            names = inner("ps", "-a", "--filter", "label=io.leroy.run=" + run_id, "--format", "{{.Names}}").split()
            if run["status"] in ("failed", "interrupted") and not names:
                break
            time.sleep(3)
        else:
            raise TimeoutError("Reaping incomplete: " + run_id)
        remaining = inner("volume", "ls", "-q").split()
        assert not set([*volumes, worker + "-work"]).intersection(remaining)
        (folder / "nas-run.json").write_text(json.dumps(run, indent=2) + "\n")
        evidence = {"passed": True, "run": run_id, "status": run["status"],
                    "runner_image": deployment["image"], "worker_removed": True,
                    "nested_helper_removed": True, "anonymous_volumes_removed": True,
                    "work_volume_removed": True, "production_modified": False}
        (folder / "nas.json").write_text(json.dumps(evidence, indent=2) + "\n")
        print(json.dumps(evidence), flush=True)


if __name__ == "__main__":
    main()

"""Run an explicit diagnostic in the owned NAS test profile and retain every result."""

import json
import re
import time
from contextlib import closing

from compare_nas_antares import client
from compare_nas_job import collect_artifacts
from nas_measurement_guard import begin, finish
from nas_ssh import ROOT

from leroy.schema import Pipeline, Step


def validate_retained_probe(folder, name, program, profile, timeout, secrets, artifacts):
    """An older receipt is usable only for the identical diagnostic definition."""
    definition = Pipeline.model_validate_json((folder / "definition.json").read_text())
    assert definition.profile == profile and definition.timeout == timeout + 60
    assert definition.source == {"kind": "diagnostic", "scenario": name}
    assert len(definition.steps) == 1
    assert definition.steps[0] == Step(
        id="probe", name=name, command=["python", "-c", program], timeout=timeout,
        secrets=list(secrets), artifacts=list(artifacts),
    ), "Diagnostic name already belongs to a different probe; retain it and use a distinct name"


def execute(name, program, *, secrets=(), timeout=240, artifacts=(), poll_seconds=3, profile="graphato"):
    assert re.fullmatch(r"[a-z0-9-]+", name)
    folder = ROOT / "test-results/nas-parity/followup" / name
    folder.mkdir(parents=True, exist_ok=True)
    marker = folder / "run-id.json"
    with closing(client()) as api:
        if marker.exists():
            # A receipt from a different program/profile cannot prove this probe.
            validate_retained_probe(folder, name, program, profile, timeout, secrets, artifacts)
            run_id = json.loads(marker.read_text())["id"]
        else:
            production_before = begin(folder, 'diagnostic')
            for status in ("queued", "running", "waiting"):
                response = api.get("/api/runs", params={"status": status})
                response.raise_for_status()
                assert not response.json(), "Wait for running NAS tests"
            response = api.get("/api/pipelines")
            response.raise_for_status()
            assert not any(p["enabled"] for p in response.json())
            current = next(p for p in response.json() if p["id"] == "leroy-nas-diagnostics")
            assert current["spec"]["source"].get("kind") == "diagnostic"
            spec = Pipeline(
                id=current["id"],
                name="NAS-Abnahme: " + name,
                group="Abnahme",
                enabled=False,
                profile=profile,
                timeout=timeout + 60,
                source={"kind": "diagnostic", "scenario": name},
                steps=[
                    Step(
                        id="probe",
                        name=name,
                        command=["python", "-c", program],
                        timeout=timeout,
                        secrets=list(secrets),
                        artifacts=list(artifacts),
                    )
                ],
            )
            (folder / "definition.json").write_text(spec.model_dump_json(indent=2))
            api.put("/api/pipelines/" + spec.id, json=spec.model_dump()).raise_for_status()
            response = api.post("/api/pipelines/" + spec.id + "/runs", json={})
            response.raise_for_status()
            run_id = response.json()["id"]
            marker.write_text(json.dumps({"id": run_id, "production_guard_before": production_before}) + "\n")
        deadline = time.monotonic() + timeout + 180
        while time.monotonic() < deadline:
            response = api.get("/api/runs/" + run_id)
            response.raise_for_status()
            run = response.json()
            if run["status"] not in ("queued", "running", "waiting"):
                break
            time.sleep(poll_seconds)
        else:
            raise TimeoutError("Diagnostic still active: " + run_id)
        (folder / "run.json").write_text(json.dumps(run, indent=2) + "\n")
        response = api.get(f"/api/runs/{run_id}/logs/probe")
        response.raise_for_status()
        log = response.json()["text"]
        (folder / "console.log").write_text(log, encoding="utf-8")
        collect_artifacts(api, run, folder)
        if not (folder / 'production-measurement-qualification-diagnostic.json').exists():
            finish(folder, 'diagnostic', json.loads(marker.read_text()).get('production_guard_before'))
        assert run["status"] == "succeeded", log[-1800:]
        print(name, run_id, run["status"], flush=True)
        return folder, run

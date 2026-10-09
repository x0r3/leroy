"""Sparse log messages must arrive before process exit with long SSH keys loaded."""

import json
import time
from contextlib import closing

from test_support import ROOT, api, evidence, start, wait

from leroy.schema import Pipeline, Step

with closing(api()) as client:
    spec = Pipeline(
        id="leroy-log-progress",
        name="Live progress with secret filtering",
        group="Leroy",
        steps=[
            Step(
                id="work",
                name="Sparse progress",
                secrets=["graphato-deploy"],
                command=[
                    "python",
                    "-u",
                    "-c",
                    "import time; print('first phase ready'); time.sleep(12); print('finished')",
                ],
            )
        ],
    )
    client.put("/api/pipelines/" + spec.id, json=spec.model_dump()).raise_for_status()
    run_id = start(client, spec.id)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        run = client.get("/api/runs/" + run_id).json()
        if run["steps"][0]["log_bytes"]:
            assert run["status"] == "running", "Progress was withheld until the process exited"
            log = client.get(f"/api/runs/{run_id}/logs/work").json()["text"]
            assert log == "first phase ready\n"
            break
        assert run["status"] in ("queued", "running")
        time.sleep(0.2)
    else:
        raise TimeoutError("No live progress received")
    assert wait(client, run_id)["status"] == "succeeded"
    evidence(client, run_id)
    result = {"run": run_id, "live_progress_before_exit": True, "status": "passed"}
    (ROOT / "test-results/log-progress.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))

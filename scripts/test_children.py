"""Regression for supervisor exhaustion, multiple child calls and child timeouts in real Docker."""

import json
import time
from contextlib import closing

from test_support import ROOT, api, evidence, start, wait

from leroy.schema import Pipeline, Step


def publish(client, spec):
    client.put("/api/pipelines/" + spec.id, json=spec.model_dump()).raise_for_status()


with closing(api()) as client:
    child = Pipeline(
        id="leroy-child-stress",
        name="Child capacity regression",
        group="Leroy",
        concurrency="parallel",
        steps=[
            Step(
                id="work",
                name="Real child process",
                command=["python", "-c", "import time; time.sleep(2); print('complete')"],
            )
        ],
    )
    publish(client, child)
    parent = Pipeline(
        id="leroy-parent-stress",
        name="Parent capacity regression",
        group="Leroy",
        concurrency="parallel",
        timeout=300,
        steps=[
            Step(
                id="child",
                name="Wait for child",
                action="child",
                timeout=240,
                options={"pipeline": child.id, "wait": True},
            )
        ],
    )
    publish(client, parent)
    ids = [start(client, parent.id) for _ in range(12)]
    deadline, peak = time.monotonic() + 300, 0
    while time.monotonic() < deadline:
        runs = client.get("/api/runs?pipeline=" + parent.id + "&limit=50").json()
        runs = [r for r in runs if r["id"] in ids]
        peak = max(peak, sum(r["status"] == "waiting" for r in runs))
        if all(r["status"] == "succeeded" for r in runs) and len(runs) == 12:
            break
        assert all(r["status"] in ("queued", "running", "waiting", "succeeded") for r in runs), [
            (r["id"], r["status"], r["reason"]) for r in runs
        ]
        time.sleep(1)
    else:
        raise TimeoutError("Twelve waiting parents did not drain")
    for id in ids:
        evidence(client, id)
    result = {"parents": ids, "peak_waiting_parents": peak}
    print("Twelve parents and their real child workloads completed; peak waiting:", peak, flush=True)
    parent.steps = [
        Step(
            id="child-" + str(i),
            name="Repeated child " + str(i),
            action="child",
            timeout=120,
            options={"pipeline": child.id, "wait": True},
        )
        for i in range(6)
    ]
    publish(client, parent)
    id = start(client, parent.id)
    run = wait(client, id, 180)
    assert run["status"] == "succeeded", run["reason"]
    assert len(run["children"]) == 6 and all(c["status"] == "succeeded" for c in run["children"])
    evidence(client, id)
    result["six_distinct_children"] = id
    print("Six parallel calls to the same child produced six successful runs", flush=True)
    child.steps[0].command = ["python", "-c", "import time; time.sleep(60)"]
    publish(client, child)
    parent.steps = [
        Step(
            id="timeout",
            name="Bound child wait",
            action="child",
            timeout=4,
            options={"pipeline": child.id, "wait": True},
        )
    ]
    publish(client, parent)
    id = start(client, parent.id)
    run = wait(client, id, 60)
    assert run["status"] == "failed" and run["steps"][0]["status"] == "timed_out", run["reason"]
    assert wait(client, run["children"][0]["id"], 30)["status"] in ("cancelled", "timed_out")
    evidence(client, id)
    result["child_step_timeout"] = id
    (ROOT / "test-results/children.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("Child step timeout cancelled its actual child container", flush=True)

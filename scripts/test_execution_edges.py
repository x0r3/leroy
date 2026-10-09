"""Exercise process-tree shutdown and impossible child waits on isolated Docker."""

import json
import sys
import time
from contextlib import closing

from test_support import ROOT, api, evidence, inner, start, wait

from leroy.schema import Pipeline, Step

STUBBORN_CHILD = """
import os, signal, time
from pathlib import Path
if os.fork() == 0:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    Path('/work/stubborn-child.pid').write_text(str(os.getpid()))
    print('descendant ready', flush=True)
    while True:
        time.sleep(1)
os._exit(0)
"""
CLEANUP = """
import os, time
from pathlib import Path
pid = int(Path('/work/stubborn-child.pid').read_text())
for _ in range(30):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        print('descendant gone; cleanup reached')
        break
    time.sleep(0.1)
else:
    raise AssertionError('descendant survived process-group shutdown')
"""


def publish(client, spec):
    client.put("/api/pipelines/" + spec.id, json=spec.model_dump()).raise_for_status()


def await_output(client, run_id):
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        response = client.get(f"/api/runs/{run_id}/logs/work")
        response.raise_for_status()
        if "descendant ready" in response.json()["text"]:
            return
        time.sleep(0.2)
    raise TimeoutError("The descendant never became ready")


results = {}
with closing(api()) as client:
    assert not any(p["enabled"] for p in client.get("/api/pipelines").json())
    for cancel in (False, True):
        spec = Pipeline(
            id="leroy-process-edges",
            name="Process tree termination regression",
            group="Leroy",
            timeout=120,
            steps=[
                Step(
                    id="work",
                    name="Exited leader and stubborn descendant",
                    timeout=90 if cancel else 3,
                    command=["python", "-c", STUBBORN_CHILD],
                ),
                Step(
                    id="cleanup",
                    name="Verify descendants stopped",
                    needs=["work"],
                    always=True,
                    command=["python", "-c", CLEANUP],
                ),
            ],
        )
        publish(client, spec)
        run_id = start(client, spec.id)
        try:
            await_output(client, run_id)
            if "--before" in sys.argv:
                time.sleep(22)
                run = evidence(client, run_id)
                assert run["status"] == "running" and run["steps"][0]["status"] == "running"
                results["before_timeout_left_descendant_running"] = run_id
                print("Confirmed old worker remains stuck after timeout and termination grace", flush=True)
                break
            if cancel:
                client.post(f"/api/runs/{run_id}/cancel", json={}).raise_for_status()
            run = wait(client, run_id, 45)
            assert run["status"] == ("cancelled" if cancel else "failed"), run["reason"]
            assert [s["status"] for s in run["steps"]] == [
                "cancelled" if cancel else "timed_out",
                "succeeded",
            ]
            evidence(client, run_id)
            results["descendant_cancel" if cancel else "descendant_timeout"] = run_id
            print("Descendant termination and mandatory cleanup passed:", run_id, flush=True)
        finally:
            run = client.get("/api/runs/" + run_id).json()
            if run["status"] in ("queued", "running", "waiting"):
                client.post(f"/api/runs/{run_id}/cancel", json={}).raise_for_status()
                inner("kill", "leroy-" + run_id)
                wait(client, run_id, 30)
    if "--before" not in sys.argv:
        spec = Pipeline(
            id="leroy-process-edges",
            name="Closed output regression",
            group="Leroy",
            steps=[
                Step(
                    id="work",
                    name="Keep running after closing output",
                    timeout=40,
                    command=["python", "-c", "import os,time; os.close(1); os.close(2); time.sleep(23)"],
                )
            ],
        )
        publish(client, spec)
        run_id = start(client, spec.id)
        assert wait(client, run_id, 60)["status"] == "succeeded"
        evidence(client, run_id)
        results["closed_stdout"] = run_id
        for target, shared in [("leroy-resource-child", True), ("leroy-resource-parent", False)]:
            if shared:
                publish(
                    client,
                    Pipeline(
                        id=target,
                        name=target,
                        group="Leroy",
                        resource="leroy-test-edge-resource",
                        steps=[Step(id="work", name="Must not be queued", command=["true"])],
                    ),
                )
            spec = Pipeline(
                id="leroy-resource-parent",
                name="Child deadlock prevention",
                group="Leroy",
                resource="leroy-test-edge-resource",
                steps=[
                    Step(
                        id="child",
                        name="Reject impossible child",
                        action="child",
                        options={"pipeline": target, "wait": True},
                    )
                ],
            )
            publish(client, spec)
            run_id = start(client, spec.id)
            run = wait(client, run_id, 30)
            assert run["status"] == "failed" and not run["children"]
            assert ("waiting ancestor" if shared else "cycle") in run["reason"], run["reason"]
            evidence(client, run_id)
            results["resource_wait" if shared else "cycle"] = run_id
        print("Closed stdout and child deadlock regressions passed", flush=True)

name = "execution-edges-before.json" if "--before" in sys.argv else "execution-edges.json"
(ROOT / "test-results" / name).write_text(json.dumps(results, indent=2), encoding="utf-8")

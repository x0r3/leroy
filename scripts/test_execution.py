"""Exercise actual isolated job containers, failures and controller/runner restarts."""

import json
import subprocess
import time

from test_support import ROOT, api, evidence, inner, start, wait

from leroy.schema import Pipeline, Step

c = api()
results = {}


def publish(spec):
    response = c.put("/api/pipelines/" + spec.id, json=spec.model_dump())
    response.raise_for_status()


publish(
    Pipeline(
        id="leroy-regression",
        name="Failure propagation regression",
        group="Leroy",
        steps=[
            Step(id="fail", name="Deliberately fail", command=["python", "-c", "raise SystemExit(17)"]),
            Step(
                id="blocked",
                name="Must not execute",
                needs=["fail"],
                command=["python", "-c", "raise AssertionError('must not run')"],
            ),
            Step(
                id="descendant",
                name="Must not execute transitively",
                needs=["blocked"],
                command=["python", "-c", "raise AssertionError('must not run')"],
            ),
            Step(
                id="cleanup",
                name="Always clean up",
                needs=["descendant"],
                always=True,
                command=["python", "-c", "print('cleanup completed')"],
            ),
        ],
    )
)
rid = start(c, "leroy-regression")
run = wait(c, rid)
assert run["status"] == "failed"
assert [s["status"] for s in run["steps"]] == ["failed", "skipped", "skipped", "succeeded"]
assert all(s["log_bytes"] == 0 for s in run["steps"][1:3])
evidence(c, rid)
results["transitive_failure"] = rid
print("Transitive failure and mandatory cleanup passed", flush=True)

publish(
    Pipeline(
        id="leroy-child",
        name="Child lifecycle validation",
        group="Leroy",
        steps=[Step(id="work", name="Child workload", command=["python", "-c", "print('child completed')"])],
    )
)
publish(
    Pipeline(
        id="leroy-parent",
        name="Parent lifecycle validation",
        group="Leroy",
        steps=[
            Step(
                id="child",
                name="Wait for real child",
                action="child",
                options={"pipeline": "leroy-child", "wait": True},
            )
        ],
    )
)
rid = start(c, "leroy-parent")
run = wait(c, rid)
assert run["status"] == "succeeded", run["reason"]
assert len(run["children"]) == 1 and run["children"][0]["status"] == "succeeded"
events = c.get("/api/runs/" + rid + "/events").json()
assert any(e["kind"] == "run.waiting" for e in events)
evidence(c, rid)
results["child_wait_resume"] = rid
print("Durable child queue and parent resume passed", flush=True)

rid = start(c, "leroy-demo", {"SECONDS": 40})
for _ in range(60):
    run = c.get("/api/runs/" + rid).json()
    if any(s["id"] == "unit" and s["status"] == "running" for s in run["steps"]):
        break
    time.sleep(1)
else:
    raise TimeoutError("Restart test did not start")
subprocess.run(
    [
        "docker",
        "compose",
        "-p",
        "leroy-test",
        "-f",
        "compose.yaml",
        "-f",
        "compose.test.yaml",
        "restart",
        "controller",
        "runner",
    ],
    cwd=ROOT,
    check=True,
    capture_output=True,
)
for _ in range(30):
    try:
        c = api()
        break
    except Exception:
        time.sleep(1)
run = wait(c, rid, 120)
assert run["status"] == "succeeded", run["reason"]
assert len(run["artifacts"]) == 1
evidence(c, rid)
results["controller_runner_restart"] = rid
print("Controller and runner restart preserved active work and artifact", flush=True)


def running_work(run_id):
    for _ in range(60):
        detail = c.get("/api/runs/" + run_id).json()
        if any(s["id"] == "unit" and s["status"] == "running" for s in detail["steps"]):
            return
        time.sleep(1)
    raise TimeoutError("Test workload did not start")


rid = start(c, "leroy-demo", {"SECONDS": 60})
running_work(rid)
c.post("/api/runs/" + rid + "/cancel", json={}).raise_for_status()
assert wait(c, rid, 60)["status"] == "cancelled"
evidence(c, rid)
results["active_cancellation"] = rid
print("Active process cancellation passed", flush=True)

original = next(p["spec"] for p in c.get("/api/pipelines").json() if p["id"] == "leroy-demo")
try:
    publish(Pipeline.model_validate({**original, "concurrency": "replace"}))
    older = start(c, "leroy-demo", {"SECONDS": 60})
    running_work(older)
    newer = start(c, "leroy-demo", {"SECONDS": 0})
    assert wait(c, older, 60)["status"] == "cancelled"
    assert wait(c, newer, 60)["status"] == "succeeded"
    evidence(c, older)
    evidence(c, newer)
    results["replace_active_run"] = [older, newer]
finally:
    publish(Pipeline.model_validate(original))
print("Replacement cancelled obsolete work and completed the new attempt", flush=True)

rid = start(c, "leroy-demo", {"SECONDS": 60})
running_work(rid)
inner("kill", "leroy-" + rid)
assert wait(c, rid, 120)["status"] in ("failed", "interrupted")
evidence(c, rid)
results["worker_crash"] = rid
print("Worker crash is terminal and never reported as success", flush=True)
try:
    publish(Pipeline.model_validate({**original, "timeout": 3}))
    rid = start(c, "leroy-demo", {"SECONDS": 20})
    assert wait(c, rid, 45)["status"] == "timed_out"
    evidence(c, rid)
    results["pipeline_timeout"] = rid
finally:
    publish(Pipeline.model_validate(original))
print("Pipeline timeout has a distinct terminal status", flush=True)
(ROOT / "test-results/execution.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

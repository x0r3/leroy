"""Verify restart recovery, capacity and process termination on the owned NAS stack."""

import json
import time
from contextlib import closing

from compare_nas_antares import client
from compare_nas_job import collect_artifacts
from nas_followup_support import inner, remote
from nas_ssh import ROOT

from leroy.schema import Pipeline, Step

FOLDER = ROOT / "test-results/nas-parity/followup/nas-lifecycle"
JOB = "leroy-nas-diagnostics"
ACTIVE = ("running", "queued", "waiting")
WORK = """
import json,os,pathlib,time
path=pathlib.Path('execution.json')
with path.open('x') as output:json.dump({'pid':os.getpid(),'started':time.time()},output)
print('work started once',flush=True)
for tick in range(75):
 print('tick',tick,flush=True)
 time.sleep(1)
print('work finished',flush=True)
"""
STUBBORN = """
import os,pathlib,signal,time
if os.fork()==0:
 signal.signal(signal.SIGTERM,signal.SIG_IGN)
 pathlib.Path('child.pid').write_text(str(os.getpid()))
 print('descendant ready',flush=True)
 while True:time.sleep(1)
os._exit(0)
"""
CLEANUP = """
import os,pathlib,time
pid=int(pathlib.Path('child.pid').read_text())
for _ in range(50):
 try:os.kill(pid,0)
 except ProcessLookupError:break
 time.sleep(.1)
else:raise AssertionError('descendant survived cancellation')
print('descendant gone; cleanup completed',flush=True)
"""


def read(api, run_id):
    response = api.get("/api/runs/" + run_id)
    response.raise_for_status()
    return response.json()


def wait(api, run_id, predicate, seconds=240):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        run = read(api, run_id)
        if predicate(run):
            return run
        time.sleep(2)
    raise TimeoutError(run_id)


def finished(api, run_id):
    return wait(api, run_id, lambda run: run["status"] not in ACTIVE)


def evidence(api, run):
    output = FOLDER / run["id"]
    output.mkdir(exist_ok=True)
    (output / "run.json").write_text(json.dumps(run, indent=2) + "\n")
    collect_artifacts(api, run, output)
    for step in run["steps"]:
        response = api.get(f"/api/runs/{run['id']}/logs/{step['id']}")
        response.raise_for_status()
        (output / (step["id"] + ".log")).write_text(response.json()["text"], encoding="utf-8")


def main():
    FOLDER.mkdir(parents=True, exist_ok=True)
    marker = FOLDER / "state.json"
    assert not marker.exists(), "Inspect previous lifecycle evidence before an explicit new attempt"
    state = {}

    def record():
        marker.write_text(json.dumps(state, indent=2) + "\n")

    with closing(client()) as api:
        assert not any(p["enabled"] for p in api.get("/api/pipelines").json())
        for status in ACTIVE:
            assert not api.get("/api/runs", params={"status": status}).json()
        assert json.loads(inner("inspect", "jenkins-parity", "--format", "{{json .State.Running}}")) is False

        def publish(steps, scenario):
            spec = Pipeline(
                id=JOB,
                name="NAS-Abnahme: " + scenario,
                group="Abnahme",
                enabled=False,
                profile="graphato",
                timeout=420,
                concurrency="parallel",
                source={"kind": "diagnostic", "scenario": scenario},
                steps=steps,
            )
            api.put("/api/pipelines/" + JOB, json=spec.model_dump()).raise_for_status()

        def start(label):
            response = api.post("/api/pipelines/" + JOB + "/runs", json={})
            response.raise_for_status()
            state[label] = response.json()["id"]
            record()
            return state[label]

        def active(run_id):
            return wait(
                api,
                run_id,
                lambda run: any(s["id"] == "work" and s["status"] == "running" for s in run["steps"]),
                90,
            )

        publish(
            [
                Step(
                    id="work",
                    name="Restart continuity",
                    command=["python", "-c", WORK],
                    timeout=240,
                    artifacts=["execution.json"],
                )
            ],
            "restart and queue",
        )
        first = start("restart_run")
        active(first)
        second = start("queued_run")
        time.sleep(3)
        assert read(api, second)["status"] == "queued", "Configured capacity 1 must be enforced"
        before = json.loads(inner("inspect", "leroy-" + first, "--format", "{{json .State}}"))
        program = """import json,pathlib,subprocess
assert pathlib.Path('/volume1/docker/leroy-nas-parity/.leroy-owned').is_file()
names=['leroy-nas-parity-controller-1','leroy-nas-parity-runner-1']
for name in names:
 info=json.loads(subprocess.check_output(['docker','inspect',name]))[0]
 assert info['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity'
subprocess.run(['docker','restart',*names],check=True,capture_output=True,timeout=90)
print('Only owned controller and runner restarted')
"""
        remote(program, timeout=120)
        for _ in range(40):
            try:
                response = api.get("/health/ready")
                response.raise_for_status()
                break
            except Exception:
                time.sleep(1)
        else:
            raise TimeoutError("Controller did not recover")
        after = json.loads(inner("inspect", "leroy-" + first, "--format", "{{json .State}}"))
        assert after["Running"] and before["StartedAt"] == after["StartedAt"]
        one, two = finished(api, first), finished(api, second)
        for run in (one, two):
            evidence(api, run)
            assert run["status"] == "succeeded" and len(run["artifacts"]) == 1
            log = (FOLDER / run["id"] / "work.log").read_text()
            assert log.count("work started once") == 1 and log.count("work finished") == 1
            assert all("tick " + str(tick) + "\n" in log for tick in range(75))
        assert two["started_at"] >= one["finished_at"]
        state["active_work_survived_restart_without_replay"] = True
        state["capacity_one_and_queue_recovery"] = True
        record()
        print("NAS controller/runner restart and queue recovery passed", flush=True)

        publish(
            [
                Step(id="work", name="Stubborn descendant", command=["python", "-c", STUBBORN], timeout=240),
                Step(
                    id="cleanup",
                    name="Verify terminated descendant",
                    command=["python", "-c", CLEANUP],
                    needs=["work"],
                    always=True,
                ),
            ],
            "cancellation",
        )
        run_id = start("cancel_run")
        active(run_id)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if "descendant ready" in api.get(f"/api/runs/{run_id}/logs/work").json()["text"]:
                break
            time.sleep(1)
        else:
            raise TimeoutError("Descendant not ready")
        api.post("/api/runs/" + run_id + "/cancel", json={}).raise_for_status()
        cancelled = finished(api, run_id)
        evidence(api, cancelled)
        assert cancelled["status"] == "cancelled"
        assert [s["status"] for s in cancelled["steps"]] == ["cancelled", "succeeded"]
        state["descendant_termination_and_cleanup"] = True
        record()
        print("NAS cancellation and mandatory cleanup passed", flush=True)

        publish(
            [Step(id="work", name="Crash recognition", command=["python", "-c", WORK], timeout=240)],
            "worker crash",
        )
        run_id = start("crash_run")
        active(run_id)
        inner("kill", "leroy-" + run_id)
        crashed = finished(api, run_id)
        evidence(api, crashed)
        assert crashed["status"] in ("failed", "interrupted")
        state["worker_crash_never_reported_as_success"] = True
        state["passed"] = True
        record()
        print(json.dumps(state), flush=True)


if __name__ == "__main__":
    main()

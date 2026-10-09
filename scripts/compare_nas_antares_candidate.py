"""Exercise an explicitly staged Antares candidate with unchanged Jenkins gates."""

import argparse
import json
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from contextlib import closing

from compare_nas_antares import client
from compare_nas_job import collect_artifacts
from nas_followup_support import (
    inner,
    jenkins_api,
    production_jobs,
    start_jenkins,
    wait_production_build,
    wait_production_jobs,
)
from nas_ssh import ROOT


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["jenkins", "leroy"])
    parser.add_argument("--via-leroy", action="store_true", help="Check the owned stopped Jenkins through a manual worker")
    parser.add_argument("--compare-failed-jenkins", action="store_true", help="Compare the actual failed Jenkins gates without claiming acceptance")
    parser.add_argument("--checkout", default=str(ROOT / ".sources/antares-nas-validation"))
    parser.add_argument("--execution-pool", help="Use the dedicated Linux pool recorded by the Jenkins comparison")
    parser.add_argument(
        "--retry-reason", help="Explicit setup correction; preserves the previous Jenkins build"
    )
    args = parser.parse_args()
    phase = args.phase
    assert not args.retry_reason or phase == "jenkins"
    assert not args.via_leroy or phase == "leroy", "Use compare_nas_antares_via_leroy.py for Jenkins"
    checkout = (ROOT / args.checkout).resolve()
    assert checkout.is_relative_to((ROOT / ".sources").resolve())
    assert not subprocess.check_output(["git", "-C", str(checkout), "status", "--porcelain"]).strip()
    commit = subprocess.check_output(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True
    ).strip()
    folder = ROOT / "test-results/nas-parity/followup/candidates/antares" / commit
    staged = json.loads((folder / "staged.json").read_text())
    marker = folder / "comparison.json"
    state = (
        json.loads(marker.read_text())
        if marker.exists()
        else {
            "commit": commit,
            "original_commit": staged["original_commit"],
            "application_patches_applied": True,
        }
    )
    pool = None
    profile = "antares"
    if args.execution_pool:
        path = (ROOT / args.execution_pool).resolve()
        assert path.is_relative_to((ROOT / "test-results/nas-parity/followup/linux-pool").resolve())
        pool = json.loads(path.read_text())
        assert phase == "leroy" and args.via_leroy
        assert state["execution_pool"] == pool and pool["candidate"] == commit
        profile = pool["profile"]

    def save():
        marker.write_text(json.dumps(state, indent=2) + "\n")

    if phase == "jenkins":
        wait_production_build()
        start_jenkins()
        if args.retry_reason:
            previous = state["jenkins"]
            assert previous["result"] not in (None, "SUCCESS") and not previous["building"]
            assert not state.get("leroy_run"), "Do not replace an existing paired comparison"
            log = folder / "jenkins-console.log"
            archived = folder / f"jenkins-{previous['number']}-console.log"
            if archived.exists():
                assert archived.read_bytes() == log.read_bytes()
            else:
                archived.write_bytes(log.read_bytes())
            for name in ("jenkins-before.xml", "jenkins-candidate.xml"):
                source = folder / name
                if source.exists():
                    destination = folder / f"jenkins-{previous['number']}-{name.removeprefix('jenkins-')}"
                    if destination.exists():
                        assert destination.read_bytes() == source.read_bytes()
                    else:
                        destination.write_bytes(source.read_bytes())
            state.setdefault("jenkins_attempts", []).append(
                {"build": previous, "console": archived.name, "retry_reason": args.retry_reason}
            )
            state.pop("jenkins")
            state.pop("jenkins_number")
            save()
        if "jenkins_number" not in state:
            with closing(client()) as api:
                for status in ("queued", "running", "waiting"):
                    assert not api.get("/api/runs", params={"status": status}).json()
                assert not any(p["enabled"] for p in api.get("/api/pipelines").json())
            jobs = json.loads(jenkins_api("/api/json?tree=jobs[name,lastBuild[building]]")["text"])
            assert not any(j.get("lastBuild", {}).get("building") for j in jobs["jobs"])
            original = jenkins_api("/job/antares-ci/config.xml")["text"]
            (folder / "jenkins-before.xml").write_text(original)
            xml = ET.fromstring(original)
            xml.find(".//hudson.plugins.git.UserRemoteConfig/url").text = staged["source"]
            candidate = ET.tostring(xml, encoding="unicode")
            (folder / "jenkins-candidate.xml").write_text(candidate)
            jenkins_api("/job/antares-ci/config.xml", candidate, "application/xml")
            job = json.loads(jenkins_api("/job/antares-ci/api/json?tree=nextBuildNumber")["text"])
            state["jenkins_number"] = job["nextBuildNumber"]
            save()
            jenkins_api("/job/antares-ci/build", "", "application/x-www-form-urlencoded")
            print("Jenkins Antares candidate:", commit, "build", state["jenkins_number"], flush=True)
        deadline = time.monotonic() + 2400
        path = "/job/antares-ci/" + str(state["jenkins_number"])
        previous = None
        while time.monotonic() < deadline:
            try:
                result = json.loads(
                    jenkins_api(
                        path
                        + "/api/json?tree=number,result,building,timestamp,duration,actions[lastBuiltRevision[SHA1]]"
                    )["text"]
                )
            except RuntimeError:
                time.sleep(5)
                continue
            if not result["building"]:
                break
            console = jenkins_api(path + "/consoleText")["text"]
            stages = re.findall(r"\[Pipeline\] \{ \(([^)]+)\)", console)
            if stages and stages[-1] != previous:
                previous = stages[-1]
                print("Jenkins Antares stage:", previous, flush=True)
            time.sleep(30)
        else:
            raise TimeoutError("Jenkins candidate did not finish")
        console = jenkins_api(path + "/consoleText")["text"]
        (folder / "jenkins-console.log").write_text(console, encoding="utf-8")
        (folder / f"jenkins-{state['jenkins_number']}-console.log").write_text(console, encoding="utf-8")
        assert "Checking out Revision " + commit in console
        state["jenkins"] = result
        save()
        inner("stop", "jenkins-parity", timeout=240)
        print(json.dumps(result), flush=True)
        if result["result"] != "SUCCESS":
            print(console[-5500:], flush=True)
            raise SystemExit(1)
        return
    jenkins = state.get("jenkins", {})
    assert jenkins.get("result") and not jenkins.get("building"), "Complete and inspect Jenkins first"
    assert jenkins["result"] == "SUCCESS" or args.compare_failed_jenkins, "Explicit failed-build comparison required"
    if "leroy_run" not in state:
        state["leroy_production_jobs_before"] = wait_production_jobs()
        wait_production_build()
    if args.via_leroy and "leroy_run" not in state:
        from nas_diagnostic import execute
        from watch_nas_graphato_via_leroy import JENKINS_ID

        program = "EXPECTED=" + repr(pool["jenkins_id"] if pool else JENKINS_ID) + "\nCPUS=" + repr(state["resource_comparison"]["jenkins_cpus"]) + "\nMEMORY=" + repr(state["resource_comparison"]["jenkins_memory"]) + "\n" + r"""
import json,os,pathlib,subprocess
info=json.loads(subprocess.check_output(['docker','inspect','jenkins-parity'],text=True))[0]
assert info['Id']==EXPECTED and not info['State']['Running']
worker=json.loads(subprocess.check_output(['docker','inspect',os.environ['HOSTNAME']],text=True))[0]
budget={key:worker['HostConfig'][key] for key in ('Memory','MemorySwap','NanoCpus')}
assert budget['Memory']==MEMORY and budget['NanoCpus']==int(CPUS*1_000_000_000)
assert os.environ['NODE_OPTIONS']=='--max-old-space-size=2048'
toolchain={tool:subprocess.check_output([tool,'--version'],text=True,timeout=30).strip() for tool in ('node','npm','git','docker')}
for plugin in ('compose','buildx'):
 result=subprocess.run(['docker',plugin,'version'],text=True,capture_output=True,timeout=30)
 toolchain[plugin]=result.stdout.strip() if result.returncode==0 else 'unavailable'
images={name:json.loads(subprocess.check_output(['docker','image','inspect',name],text=True,timeout=30))[0]['Id'] for name in ('postgres:18.4-alpine3.24','mcr.microsoft.com/playwright:v1.61.1-noble')}
pathlib.Path('resource-probe.json').write_text(json.dumps({'jenkins_stopped':True,'jenkins_id':EXPECTED,'worker_budget':budget,'node_options':os.environ['NODE_OPTIONS'],'toolchain':toolchain,'shared_service_images':images,'job_image':worker['Image']}))
"""
        probe, diagnostic = execute(
            "antares-leroy-preflight-" + commit[:12] + "-jenkins" + str(jenkins["number"]), program, timeout=90,
            artifacts=["resource-probe.json"], profile=profile,
        )
        state["leroy_resource_probe"] = {
            "run": diagnostic["id"],
            **json.loads((probe / "leroy-artifacts/probe/resource-probe.json").read_text()),
        }
        save()
        identity = state["resource_comparison"]
        actual = state["leroy_resource_probe"]
        assert actual["worker_budget"] == {
            "Memory": identity["jenkins_memory"],
            "MemorySwap": identity["memory_swap_both"],
            "NanoCpus": int(identity["jenkins_cpus"] * 1_000_000_000),
        }
        assert actual["node_options"] == identity["node_options"]
        assert actual["toolchain"] == identity["toolchains"]["jenkins"]
        assert actual["shared_service_images"] == identity["shared_service_images"]
        assert actual["job_image"] == identity["job_images"]["leroy"]
    elif not args.via_leroy:
        assert json.loads(inner("inspect", "jenkins-parity", "--format", "{{json .State.Running}}")) is False
    with closing(client()) as api:
        if "leroy_run" not in state:
            pipelines = api.get("/api/pipelines").json()
            assert not any(p["enabled"] for p in pipelines)
            original = next(p["spec"] for p in pipelines if p["id"] == "antares-ci")
            (folder / "leroy-before.json").write_text(json.dumps(original, indent=2) + "\n")
            spec = {
                **original,
                "profile": profile,
                "repository": staged["source"],
                "source": {**original["source"], "commit": commit},
            }
            api.put("/api/pipelines/antares-ci", json=spec).raise_for_status()
            response = api.post("/api/pipelines/antares-ci/runs", json={"commit": commit})
            response.raise_for_status()
            state["leroy_run"] = response.json()["id"]
            save()
            print("Leroy Antares candidate:", state["leroy_run"], flush=True)
        deadline = time.monotonic() + 2400
        previous = None
        while time.monotonic() < deadline:
            response = api.get("/api/runs/" + state["leroy_run"])
            response.raise_for_status()
            run = response.json()
            if run["status"] not in ("queued", "running", "waiting"):
                break
            active = [s["id"] for s in run["steps"] if s["status"] == "running"]
            if active != previous:
                print("Leroy Antares stage:", active, flush=True)
                previous = active
            time.sleep(10)
        else:
            raise TimeoutError(state["leroy_run"])
        (folder / "leroy-run.json").write_text(json.dumps(run, indent=2) + "\n")
        collect_artifacts(api, run, folder)
        for step in run["steps"]:
            offset = 0
            with (folder / ("leroy-" + step["id"] + ".log")).open("w", encoding="utf-8") as output:
                while offset < step["log_bytes"]:
                    response = api.get(f"/api/runs/{run['id']}/logs/{step['id']}", params={"offset": offset})
                    response.raise_for_status()
                    block = response.json()
                    output.write(block["text"])
                    assert block["next_offset"] > offset
                    offset = block["next_offset"]
        state["leroy_status"] = run["status"]
        if "leroy_production_jobs_before" in state:
            state["leroy_production_jobs_after"] = production_jobs()
            state["leroy_production_jobs_unchanged"] = (
                state["leroy_production_jobs_before"]["jobs"] == state["leroy_production_jobs_after"]["jobs"]
            )
        state["execution_success_both"] = run["status"] == "succeeded" and jenkins["result"] == "SUCCESS"
        if not state.get("complete_matching_gates"):
            state["workload_success_both"] = False
        save()
        print(json.dumps(state), flush=True)
        assert run["status"] == "succeeded", run["reason"]


if __name__ == "__main__":
    main()

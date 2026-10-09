"""Compare the real two-image build/push path using the same original diff base."""

import json
import time
import urllib.parse
import xml.etree.ElementTree as ET
from contextlib import closing

from compare_nas_antares import client
from compare_nas_job import collect_artifacts
from nas_followup_support import inner, jenkins_api, start_jenkins, wait_production_build
from nas_ssh import ROOT

BASE = "d77449890b1e0f597f55b477e7c99c3ea1f68735"
COMMIT = "9fb528a1bb4b736d53d294510b374d516e973a03"
JOB = "leroy-home-lab-build"
FOLDER = ROOT / "test-results/nas-parity/followup/home-lab-build"


def write(name, value):
    (FOLDER / name).write_text(json.dumps(value, indent=2) + "\n")


def wait_run(api, run_id):
    until = time.monotonic() + 7200
    while time.monotonic() < until:
        response = api.get("/api/runs/" + run_id)
        response.raise_for_status()
        run = response.json()
        if run["status"] not in ("queued", "running", "waiting"):
            return run
        time.sleep(15)
    raise TimeoutError(run_id)


def images(engine):
    result = {}
    for service in ("mail-ingest-service", "yt-downloader"):
        tag = "registry:5000/home-lab/" + service + ":" + COMMIT[:12]
        image = json.loads(inner("image", "inspect", tag))[0]
        latest = json.loads(inner("image", "inspect", "registry:5000/home-lab/" + service + ":latest"))[0]
        assert image["Id"] == latest["Id"] and image["RepoDigests"]
        inner("tag", image["Id"], "leroy-parity-proof/" + engine + "/" + service + ":" + COMMIT[:12])
        result[service] = {
            "id": image["Id"],
            "digests": image["RepoDigests"],
            "latest_matches": True,
            "layers": image["RootFS"]["Layers"],
            "config": image["Config"],
        }
    write(engine + "-images.json", result)
    return result


def main():
    FOLDER.mkdir(exist_ok=True)
    marker = FOLDER / "state.json"
    state = json.loads(marker.read_text()) if marker.exists() else {"base": BASE, "commit": COMMIT}
    with closing(client()) as api:
        if "seed_run" not in state:
            installed = api.get("/api/pipelines").json()
            assert not any(p["enabled"] for p in installed)
            assert not any(p["id"] == JOB for p in installed)
            spec = next(p["spec"] for p in installed if p["id"] == "home-lab-ci")
            spec.update(id=JOB, name="Home-Lab: Buildvergleich", group="Abnahme")
            spec["source"] = {**spec["source"], "kind": "comparison", "original_pipeline": "home-lab-ci"}
            write("pipeline.json", spec)
            seed = {**spec, "steps": [spec["steps"][0]], "source": {"kind": "comparison-history-seed"}}
            api.put("/api/pipelines/" + JOB, json=seed).raise_for_status()
            response = api.post("/api/pipelines/" + JOB + "/runs", json={"commit": BASE})
            response.raise_for_status()
            state["seed_run"] = response.json()["id"]
            write("state.json", state)
        seed = wait_run(api, state["seed_run"])
        write("history-seed-run.json", seed)
        assert seed["status"] == "succeeded" and seed["commit"] == BASE
        spec = json.loads((FOLDER / "pipeline.json").read_text())
        api.put("/api/pipelines/" + JOB, json=spec).raise_for_status()
    if "jenkins" not in state:
        wait_production_build()
        start_jenkins()
        if not state.get("jenkins_started"):
            xml = ET.fromstring((ROOT / ".local/nas-parity/fixtures/home-lab-ci.xml").read_text())
            for definition in xml.findall(".//hudson.model.StringParameterDefinition"):
                if definition.findtext("name") == "GIT_PREVIOUS_SUCCESSFUL_COMMIT":
                    definition.find("defaultValue").text = BASE
            text = ET.tostring(xml, encoding="unicode")
            (FOLDER / "jenkins.xml").write_text(text)
            jenkins_api("/createItem?name=" + JOB, text, "application/xml")
            parameters = {
                "GIT_PREVIOUS_SUCCESSFUL_COMMIT": BASE,
                "CI_REGISTRY_URL": "registry:5000",
                "CI_REGISTRY_NAMESPACE": "home-lab",
            }
            jenkins_api(
                "/job/" + JOB + "/buildWithParameters",
                urllib.parse.urlencode(parameters),
                "application/x-www-form-urlencoded",
            )
            state["jenkins_started"] = True
            write("state.json", state)
            print("Jenkins real Home-Lab build started.", flush=True)
        until = time.monotonic() + 7200
        while time.monotonic() < until:
            job = json.loads(
                jenkins_api("/job/" + JOB + "/api/json?tree=lastBuild[number,building,result]")["text"]
            )
            build = job.get("lastBuild")
            if build and not build["building"]:
                break
            time.sleep(30)
        else:
            raise TimeoutError("Jenkins Home-Lab build still active")
        console = jenkins_api("/job/" + JOB + "/" + str(build["number"]) + "/consoleText")["text"]
        (FOLDER / "jenkins.log").write_text(console, encoding="utf-8")
        assert build["result"] == "SUCCESS", console[-1500:]
        assert "Diff base: " + BASE in console and "Built images: mail-ingest-service:" in console
        assert "yt-downloader:" + COMMIT[:12] in console and "Checking out Revision " + COMMIT in console
        images("jenkins")
        state["jenkins"] = build
        write("state.json", state)
        inner("stop", "jenkins-parity", timeout=240)
    with closing(client()) as api:
        if "leroy_run" not in state:
            response = api.post("/api/pipelines/" + JOB + "/runs", json={"commit": COMMIT})
            response.raise_for_status()
            state["leroy_run"] = response.json()["id"]
            write("state.json", state)
            print("Leroy real Home-Lab build:", state["leroy_run"], flush=True)
        run = wait_run(api, state["leroy_run"])
        write("leroy-run.json", run)
        collect_artifacts(api, run, FOLDER)
        for step in run["steps"]:
            response = api.get(f"/api/runs/{run['id']}/logs/{step['id']}")
            response.raise_for_status()
            (FOLDER / ("leroy-" + step["id"] + ".log")).write_text(response.json()["text"], encoding="utf-8")
        assert run["status"] == "succeeded" and run["outputs"]["diff_base"] == BASE
        assert run["outputs"]["build_required"] and len(run["outputs"]["images"]) == 2
    right = images("leroy")
    left = json.loads((FOLDER / "jenkins-images.json").read_text())
    same = all(left[name]["id"] == value["id"] for name, value in right.items())
    report = {
        **state,
        "application_patches_applied": False,
        "real_build_and_push_both": True,
        "same_image_ids": same,
        "images": {
            e: {k: v["id"] for k, v in data.items()} for e, data in [("jenkins", left), ("leroy", right)]
        },
        "history_seed_is_not_a_workload_acceptance": True,
        "cache_and_timing_not_a_performance_comparison": True,
    }
    write("comparison.json", report)
    assert same, "Image differences require content analysis; evidence preserved"
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()

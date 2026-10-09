"""Paired original-source image pipelines in the owned NAS comparison daemon."""

import argparse
import json
import time
import xml.etree.ElementTree as ET
from contextlib import closing

from compare_nas_antares import client, jenkins
from deploy_nas_parity import CREDENTIALS, LOCAL, REMOTE, remote
from nas_ssh import ROOT, upload_file

JOBS = {"home-lab-ci": "home-lab-service-collection", "nikicas-hub-ci": "nikicas-hub"}


def prepare():
    for name, repo in JOBS.items():
        root = ET.fromstring((ROOT / f"test-results/nas-parity/jenkins-configs/{name}.xml").read_text())
        properties = root.find("properties")
        properties.clear()
        definitions = ET.SubElement(
            ET.SubElement(properties, "hudson.model.ParametersDefinitionProperty"), "parameterDefinitions"
        )
        for key, value in {"CI_REGISTRY_URL": "registry:5000", "CI_REGISTRY_NAMESPACE": "home-lab"}.items():
            p = ET.SubElement(definitions, "hudson.model.StringParameterDefinition")
            ET.SubElement(p, "name").text = key
            ET.SubElement(p, "defaultValue").text = value
        scm = root.find(".//scm")
        user = scm.find("userRemoteConfigs/hudson.plugins.git.UserRemoteConfig")
        user.find("url").text = "/sources/" + repo
        for field in list(user):
            if field.tag == "credentialsId":
                user.remove(field)
        scm.find("branches/hudson.plugins.git.BranchSpec/name").text = "*/master"
        fixture = LOCAL / "fixtures" / (name + ".xml")
        fixture.write_text(ET.tostring(root, encoding="unicode"), encoding="utf-8")
        upload_file(fixture, REMOTE + "/fixtures/" + fixture.name, CREDENTIALS)
    config = LOCAL / "config/runner.toml"
    text = config.read_text()
    if "[profiles.image-builds]" not in text:
        text += """
[profiles.image-builds]
image = "leroy-job:nas-parity"
network = "leroy-jobs"
memory = "2g"
cpus = 2
docker = true
host_mappings = {controller = "10.232.98.10"}
mounts = ["type=bind,source=/sources,target=/sources,readonly"]
[profiles.image-builds.environment]
DOCKER_BUILDKIT = "0"
CI_REGISTRY_URL = "registry:5000"
CI_REGISTRY_NAMESPACE = "home-lab"
"""
        config.write_text(text, encoding="utf-8")
    upload_file(config, REMOTE + "/config/runner.toml", CREDENTIALS)
    remote(
        f"""cd {REMOTE}
    chmod 644 fixtures/home-lab-ci.xml fixtures/nikicas-hub-ci.xml config/runner.toml
    docker compose up -d --force-recreate runner
    docker exec leroy-nas-parity-docker-1 docker run -d --name registry --network leroy-jobs --ip 10.234.98.2 \
      --label io.leroy.nas-parity=true registry:2
    registry_ip=$(docker exec leroy-nas-parity-docker-1 docker inspect --format '{{{{range .NetworkSettings.Networks}}}}{{{{.IPAddress}}}}{{{{end}}}}' registry)
    docker exec leroy-nas-parity-docker-1 sh -c "printf '%s registry\\n' '$registry_ip' >> /etc/hosts"
    docker exec leroy-nas-parity-docker-1 docker start jenkins-parity
    """,
        timeout=180,
    )
    for attempt in range(45):
        try:
            # Reuse the completed Antares job only for an authenticated readiness read.
            jenkins("status")
            break
        except (RuntimeError, json.JSONDecodeError):
            if attempt == 44:
                raise
            time.sleep(2)
    with closing(client()) as api:
        installed = {p["id"]: p for p in api.get("/api/pipelines").json()}
        for name in JOBS:
            spec = installed[name]["spec"]
            spec["profile"] = "image-builds"
            spec["enabled"] = False
            response = api.put("/api/pipelines/" + name, json=spec)
            response.raise_for_status()
            print(name, jenkins("configure", name), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--round", choices=["initial", "aligned"], default="initial")
    parser.add_argument("phase", choices=["prepare", "start-jenkins", "jenkins", "start-leroy", "leroy"])
    parser.add_argument("--pipeline", choices=list(JOBS))
    args = parser.parse_args()
    if args.phase == "prepare":
        prepare()
        return
    if not args.pipeline:
        parser.error("--pipeline is required")
    directory = ROOT / "test-results/nas-parity"
    if args.round == "aligned":
        directory = directory / "aligned"
    directory = directory / args.pipeline
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "pair.json"
    baseline = json.loads((ROOT / "test-results/nas-parity/baseline.json").read_text())
    state = (
        json.loads(path.read_text())
        if path.exists()
        else {
            "pipeline": args.pipeline,
            "commit": baseline["sources"][JOBS[args.pipeline]]["commit"],
            "complete": False,
            "application_patches_applied": False,
        }
    )
    if args.phase == "start-jenkins":
        if state.get("jenkins_start"):
            raise ValueError("Already started; no implicit retries")
        state["jenkins_start"] = jenkins("start", args.pipeline)
    elif args.phase == "jenkins":
        result = jenkins("status", args.pipeline)
        (directory / "jenkins-console.log").write_text(result["console"], encoding="utf-8")
        state["jenkins"] = result["build"]
        print(json.dumps({k: result["build"][k] for k in ("number", "result", "building", "duration")}))
        print(result["console"][-900:])
    elif args.phase == "start-leroy":
        if state.get("leroy_run"):
            raise ValueError("Already started; no implicit retries")
        if not state.get("jenkins", {}).get("result") or state["jenkins"].get("building"):
            raise ValueError("Jenkins baseline is not complete")
        with closing(client()) as api:
            r = api.post(
                "/api/pipelines/" + args.pipeline + "/runs",
                json={"parameters": {}, "commit": state["commit"]},
            )
            r.raise_for_status()
            state["leroy_run"] = r.json()["id"]
            print("Leroy run", state["leroy_run"])
    else:
        with closing(client()) as api:
            r = api.get("/api/runs/" + state["leroy_run"])
            r.raise_for_status()
            run = r.json()
            (directory / "leroy-run.json").write_text(json.dumps(run, indent=2), encoding="utf-8")
            for step in run["steps"]:
                offset = 0
                with (directory / ("leroy-" + step["id"] + ".log")).open("w", encoding="utf-8") as stream:
                    while offset < step["log_bytes"]:
                        r = api.get(f"/api/runs/{run['id']}/logs/{step['id']}", params={"offset": offset})
                        r.raise_for_status()
                        log = r.json()
                        stream.write(log.get("text", ""))
                        if log.get("next_offset", offset) <= offset:
                            break
                        offset = log["next_offset"]
            state["leroy_status"] = run["status"]
            print(
                json.dumps(
                    {
                        "run": run["id"],
                        "status": run["status"],
                        "steps": [(s["id"], s["status"]) for s in run["steps"]],
                    },
                    indent=2,
                )
            )
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

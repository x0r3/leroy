"""Run a short real job in every pinned profile after the owned stack restart."""

import argparse
import hashlib
import json
import re
import time
import uuid
from contextlib import closing
from datetime import datetime, timezone

from compare_nas_antares import client
from nas_gitea_target import idle
from nas_ssh import ROOT

from leroy.schema import Pipeline, Step


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--restart-attempt", help="Explicit successful retained restart attempt")
    args = parser.parse_args()
    assert re.fullmatch(r"[a-f0-9]{40}", args.commit)
    base = ROOT / "test-results/nas-parity/followup/candidates/graphato" / args.commit
    pins = read(base / "release-image-pins.json")
    before = read(base / "nas-release-configuration-before.json")
    assert pins["tested_image_layers_unchanged"] and not pins["production_modified"]
    attempt = args.restart_attempt or "master-" + args.commit[:12]
    assert re.fullmatch(r"[a-z0-9-]{1,64}", attempt)
    restart = ROOT / "test-results/nas-parity/followup/nas-stack-restart/attempts" / attempt / "report.json"
    assert read(restart)["passed"]
    folder = base / "release-image-smoke"
    assert not folder.exists(), "Inspect retained smoke jobs before an explicit new attempt"
    idle()
    folder.mkdir()
    identifier = "leroy-nas-diagnostics"
    verified = {}
    with closing(client()) as api:
        response = api.get("/api/pipelines")
        response.raise_for_status()
        definitions = response.json()
        assert not any(row["enabled"] for row in definitions)
        previous = next(row["spec"] for row in definitions if row["id"] == identifier)
        assert previous["source"]["kind"] == "diagnostic"
        write(folder / "previous-definition.json", previous)
        try:
            for profile, expected in sorted(before["job_profiles"].items()):
                assert pins["job_images"][profile] == expected["image_id"]
                target = folder / profile
                target.mkdir()
                nonce = uuid.uuid4().hex
                program = ("import json,pathlib,platform\n"
                           "root=pathlib.Path('/sys/fs/cgroup')\n"
                           "data={'profile':" + repr(profile) + ", 'nonce':" + repr(nonce) +
                           ", 'python':platform.python_version(), 'cgroup':{name:(root/name).read_text().strip() "
                           "for name in ('memory.max','memory.swap.max','cpu.max')}}\n"
                           "pathlib.Path('proof.json').write_text(json.dumps(data)+'\\n')\n"
                           "print('Pinned profile job completed',flush=True)\n")
                compile(program, "pinned-profile-smoke", "exec")
                spec = Pipeline(id=identifier, name="NAS-Test: fixierte Worker-Images", group="Abnahme",
                                enabled=False, profile=profile, timeout=180,
                                source={"kind": "diagnostic", "scenario": "pinned-job-images",
                                        "comparison_commit": args.commit, "profile": profile, "nonce": nonce},
                                steps=[Step(id="probe", name="Worker-Image prüfen", timeout=120,
                                            command=["python", "-c", program], artifacts=["proof.json"])])
                write(target / "definition.json", spec.model_dump())
                api.put("/api/pipelines/" + identifier, json=spec.model_dump()).raise_for_status()
                write(target / "start-attempt.json", {"profile": profile, "nonce": nonce})
                response = api.post("/api/pipelines/" + identifier + "/runs", json={})
                response.raise_for_status()
                run_id = response.json()["id"]
                write(target / "run-id.json", {"id": run_id})
                deadline = time.monotonic() + 240
                while time.monotonic() < deadline:
                    response = api.get("/api/runs/" + run_id)
                    response.raise_for_status()
                    run = response.json()
                    if run["status"] not in {"queued", "running", "waiting"}:
                        break
                    time.sleep(2)
                else:
                    raise TimeoutError("Retain and inspect the active smoke job: " + run_id)
                write(target / "run.json", run)
                assert run["status"] == "succeeded", "Inspect the retained smoke run; no implicit retry"
                assert run["image_digest"] == expected["image_id"]
                artifact, = [row for row in run["artifacts"] if row["name"] == "proof.json"]
                response = api.get("/api/artifacts/" + artifact["id"])
                response.raise_for_status()
                content = response.content
                assert len(content) == artifact["size"] and hashlib.sha256(content).hexdigest() == artifact["sha256"]
                (target / "proof.json").write_bytes(content)
                receipt = json.loads(content)
                assert receipt["profile"] == profile and receipt["nonce"] == nonce
                assert expected["memory"] == "2g" and expected["cpus"] == 2
                assert int(receipt["cgroup"]["memory.max"]) == 2 * 1024**3
                assert receipt["cgroup"]["cpu.max"].split() == ["200000", "100000"]
                if expected["memory_swap"] == expected["memory"]:
                    assert int(receipt["cgroup"]["memory.swap.max"]) == 0
                verified[profile] = {"run": run_id, "status": run["status"], "image_id": run["image_digest"],
                                     "artifact_sha256": artifact["sha256"], "runtime_cgroup": receipt["cgroup"]}
                print(json.dumps({"profile": profile, "run": run_id, "status": run["status"]}), flush=True)
        finally:
            api.put("/api/pipelines/" + identifier, json=previous).raise_for_status()
        definitions = api.get("/api/pipelines").json()
        assert next(row["spec"] for row in definitions if row["id"] == identifier) == previous
        assert not any(row["enabled"] for row in definitions)
    idle()
    record = {"at": datetime.now(timezone.utc).isoformat(), "commit": args.commit, "passed": True,
              "profiles": verified, "all_profile_image_ids_match": True, "artifact_hashes_match": True,
              "previous_diagnostic_definition_restored": True, "after_full_stack_restart": True,
              "production_modified": False, "application_source_changed": False,
              "scope": "Real owned NAS worker jobs; no application deployment or release approval"}
    write(base / "release-image-smoke.json", record)
    print(json.dumps({"passed": True, "profiles": list(verified)}), flush=True)


if __name__ == "__main__":
    main()

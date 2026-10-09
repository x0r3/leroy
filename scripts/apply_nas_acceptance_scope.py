"""Apply the user's NAS-only scope and stop the optional local test worker."""

import json
from contextlib import closing
from datetime import datetime, timezone

from compare_nas_antares import client
from nas_followup_support import production_jobs
from nas_ssh import ROOT
from setup_nas_linux_pool import EVIDENCE, PARENT, docker, nested


def main():
    folder = ROOT / "test-results/nas-parity/followup/production-source-review"
    marker = folder / "nas-only-scope.json"
    assert not marker.exists(), "No implicit scope reapplication"
    production_before = production_jobs()
    with closing(client()) as api:
        for status in ("queued", "running", "waiting"):
            response = api.get("/api/runs", params={"status": status})
            response.raise_for_status()
            assert not response.json()
        response = api.get("/api/pipelines")
        response.raise_for_status()
        pipelines = response.json()
        assert not any(p["enabled"] for p in pipelines)
        spec = next(p["spec"] for p in pipelines if p["id"] == "antares-ci")
        (folder / "antares-definition-before-exclusion.json").write_text(json.dumps(spec, indent=2) + "\n")
        spec["enabled"] = False
        spec["profile"] = "image-builds"
        spec["description"] = "Aus der NAS-Abnahme ausgenommen: Antares-Artefakt gemäß Nutzerentscheidung."
        spec["source"]["acceptance_excluded"] = True
        spec["source"]["acceptance_exclusion_reason"] = "NAS-only deployment; user accepts Antares build limitation"
        api.put("/api/pipelines/antares-ci", json=spec).raise_for_status()
    pool = json.loads((EVIDENCE / "pool.json").read_text())
    parent = json.loads(docker("inspect", PARENT, text=True).stdout)[0]
    assert parent["Id"] == pool["parent_id"]
    assert parent["Config"]["Labels"]["io.leroy.nas-linux-pool"] == "true"
    runner = json.loads(docker("inspect", "leroy-nas-linux-runner", text=True).stdout)[0]
    assert runner["Config"]["Labels"]["io.leroy.nas-linux-pool"] == "true"
    assert not nested("ps", "-a", "--filter", "label=io.leroy.runner=runner-nas-linux-pool",
                      "--format", "{{.ID}}", text=True).stdout.strip()
    docker("update", "--restart", "no", "leroy-nas-linux-runner", PARENT)
    docker("stop", "leroy-nas-linux-runner", PARENT, timeout=90)
    assert not any(row["State"]["Running"] for row in json.loads(
        docker("inspect", "leroy-nas-linux-runner", PARENT, text=True).stdout))
    production_after = production_jobs()
    assert production_before["jobs"] == production_after["jobs"]
    record = {"at": datetime.now(timezone.utc).isoformat(), "deployment_topology": "NAS-only controller and CI workers",
              "excluded_pipeline": "antares-ci", "included_pipeline_count": 12,
              "user_authorized_exclusion": True, "antares_definition_and_results_retained": True,
              "optional_local_linux_pool_stopped": True, "optional_local_linux_pool_auto_restart_disabled": True,
              "optional_local_linux_pool_data_retained": True, "production_jobs_unchanged": True,
              "production_modified": False, "production_cutover": False, "production_replacement_ready": False}
    marker.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record), flush=True)


if __name__ == "__main__":
    main()

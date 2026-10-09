"""Record terminal or unexecuted paths without treating matching failures as acceptance."""

import json
from datetime import datetime, timezone

from nas_ssh import ROOT
from stage_nas_production_graphato import COMMIT


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    base = ROOT / "test-results/nas-parity/followup/candidates/graphato" / COMMIT
    executions = read(base / "current-source-comparison.json")
    staged = read(base / "staged.json")
    assert not staged["application_patches_applied"] and staged["source_kind"] == "observed_production_revision"
    jenkins, leroy = executions["jenkins"]["builds"], executions["leroy"]["runs"]
    assert not any(row.get("building") for row in jenkins.values())
    assert not any(row["status"] in {"queued", "running", "waiting"} for row in leroy.values())
    bootstrap = read(base / "graphato-bootstrap-host/pair.json")
    jenkins = {**jenkins, "graphato-bootstrap-host": bootstrap["jenkins"]}
    bootstrap_run = read(base / "graphato-bootstrap-host/leroy-run.json")
    leroy = {**leroy, "graphato-bootstrap-host": {"id": bootstrap_run["id"], "status": bootstrap_run["status"]}}
    pipelines = {}
    for name in ("graphato-bootstrap-host", "graphato-ci", "graphato-release-acceptance", "graphato-postdeploy-web", "graphato-postdeploy-quality"):
        reference, observed = jenkins.get(name, {}), leroy.get(name, {})
        j_started = reference.get("started", bool(reference.get("result")))
        l_started = bool(observed.get("id"))
        pair_path = base / name / "pair.json"
        pair = read(pair_path) if pair_path.exists() else {}
        source_matches = None
        if j_started and l_started:
            run = read(base / name / "leroy-run.json")
            assert pair["commit"] in pair["jenkins"]["checkout_revisions"] and run["commit"] == pair["commit"]
            assert not pair["application_patches_applied"]
            source_matches = True
        state = "completed_execution_pending_analysis"
        if not j_started and not l_started:
            assert jenkins["graphato-ci"]["result"] != "SUCCESS" and leroy["graphato-ci"]["status"] != "succeeded"
            state = "not_executed_after_ci_failure"
        elif j_started != l_started or (reference.get("result") == "SUCCESS") != (observed.get("status") == "succeeded"):
            state = "execution_difference"
        elif reference.get("result") != "SUCCESS":
            state = "failed_execution_pending_analysis"
        pipelines[name] = {"jenkins_build": reference.get("number"), "jenkins_result": reference.get("result"),
                           "leroy_run": observed.get("id"), "leroy_status": observed.get("status"),
                           "jenkins_started": j_started, "leroy_started": l_started,
                           "source_matches": source_matches, "state": state,
                           "workload_success_both": False, "receipt_and_failure_analysis_pending": True}
    record = {"at": datetime.now(timezone.utc).isoformat(), "commit": COMMIT,
              "application_patches_applied": False, "pipelines": pipelines,
              "source_execution_recorded": True, "receipt_and_failure_analysis_pending": True,
              "same_failed_status_proves_same_cause": False,
              "performance_comparison_valid": False, "production_replacement_ready": False}
    (base / "current-source-outcomes.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({"states": {name: row["state"] for name, row in pipelines.items()}}))


if __name__ == "__main__":
    main()

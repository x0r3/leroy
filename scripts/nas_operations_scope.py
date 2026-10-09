"""Keep CI infrastructure verification distinct from application workload acceptance."""

import json


def require_operations_inputs(folder, commit, *, infrastructure_only=False):
    def read(name):
        return json.loads((folder / name).read_text())

    complete = read("master-acceptance-complete.json")
    fresh = read("current-source-analysis.json")
    prepared = read("scenarios/root-private-existing-host/analysis.json")
    assert complete["commit"] == fresh["commit"] == prepared["commit"] == commit
    assert all(not record["application_patches_applied"] for record in (complete, fresh, prepared))
    assert all(not record["production_modified"] for record in (complete, fresh, prepared))
    assert prepared["all_required_groups_executed_both"], "Finish collecting both complete workloads first"
    assert prepared["same_active_build_both"] and prepared["same_prepared_host_snapshot_both"]
    for name in ("graphato-bootstrap-host", "graphato-ci"):
        row = fresh["pipelines"][name]
        assert row["source_matches"] and row["workload_success_both"]
        assert row["jenkins_result"] == "SUCCESS" and row["leroy_status"] == "succeeded"
    assert set(prepared["pipelines"]) == {
        "graphato-release-acceptance", "graphato-postdeploy-web", "graphato-postdeploy-quality"}
    for row in prepared["pipelines"].values():
        assert row["source_matches"]
        assert row["jenkins_result"] in {"SUCCESS", "FAILURE"}
        assert row["leroy_status"] in {"succeeded", "failed"}
    for engine in ("jenkins", "leroy"):
        target = read("scenarios/root-private-existing-host/" + engine + "-target-after.json")
        assert target["manifest"]["commit"] == commit
        assert len(target["containers"]) == 4
        assert all(row["running"] and row["health"] == "healthy" for row in target["containers"])
    if not infrastructure_only:
        assert prepared["workload_success_both"] and prepared["no_migration_execution_difference_observed"], (
            "Application acceptance is not green; explicitly scope independent CI infrastructure checks")
    return {
        "infrastructure_only": infrastructure_only,
        "application_workload_success_both": prepared["workload_success_both"],
        "no_migration_execution_difference_observed": prepared["no_migration_execution_difference_observed"],
        "unaccepted_application_pipelines": [name for name, row in prepared["pipelines"].items()
                                           if not row["workload_success_both"]],
        "application_acceptance_evidence": "scenarios/root-private-existing-host/analysis.json",
        "production_replacement_ready": False,
    }

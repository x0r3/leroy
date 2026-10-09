"""Infrastructure evidence must not substitute for failed or incomplete application acceptance."""

import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def evidence(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    helper = importlib.import_module("nas_operations_scope")
    commit = "a" * 40
    identity = {"commit": commit, "application_patches_applied": False, "production_modified": False}
    scenario = "scenarios/root-private-existing-host/"
    records = {
        "master-acceptance-complete.json": identity.copy(),
        "current-source-analysis.json": {**identity, "pipelines": {
            name: {"source_matches": True, "workload_success_both": True,
                   "jenkins_result": "SUCCESS", "leroy_status": "succeeded"}
            for name in ("graphato-bootstrap-host", "graphato-ci")}},
        scenario + "analysis.json": {**identity,
            "all_required_groups_executed_both": True, "same_active_build_both": True,
            "same_prepared_host_snapshot_both": True, "workload_success_both": False,
            "no_migration_execution_difference_observed": True, "pipelines": {
                name: {"source_matches": True, "workload_success_both": False,
                       "jenkins_result": "FAILURE", "leroy_status": "failed"}
                for name in ("graphato-release-acceptance", "graphato-postdeploy-web", "graphato-postdeploy-quality")}},
    }
    for engine in ("jenkins", "leroy"):
        records[scenario + engine + "-target-after.json"] = {
            "manifest": {"commit": commit}, "containers": [{"running": True, "health": "healthy"}] * 4}

    def save():
        for name, value in records.items():
            path = tmp_path / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(value))

    save()
    return helper, tmp_path, commit, records, save


def test_red_workload_requires_explicit_infrastructure_scope_and_stays_red(evidence):
    helper, folder, commit, _, _ = evidence
    before = {path: path.read_bytes() for path in folder.rglob("*.json")}
    with pytest.raises(AssertionError, match="Application acceptance is not green"):
        helper.require_operations_inputs(folder, commit)
    scope = helper.require_operations_inputs(folder, commit, infrastructure_only=True)
    assert scope["infrastructure_only"] and not scope["application_workload_success_both"]
    assert len(scope["unaccepted_application_pipelines"]) == 3
    assert not scope["production_replacement_ready"]
    assert all(path.read_bytes() == value for path, value in before.items())


@pytest.mark.parametrize("invalid", ["incomplete", "interrupted", "other_source", "failed_build", "unhealthy"])
def test_infrastructure_scope_still_refuses_missing_execution_prerequisites(evidence, invalid):
    helper, folder, commit, records, save = evidence
    scenario = "scenarios/root-private-existing-host/"
    if invalid == "incomplete":
        records[scenario + "analysis.json"]["all_required_groups_executed_both"] = False
    elif invalid == "interrupted":
        records[scenario + "analysis.json"]["pipelines"]["graphato-postdeploy-web"]["leroy_status"] = "interrupted"
    elif invalid == "other_source":
        records[scenario + "analysis.json"]["commit"] = "b" * 40
    elif invalid == "failed_build":
        records["current-source-analysis.json"]["pipelines"]["graphato-ci"]["workload_success_both"] = False
    else:
        records[scenario + "leroy-target-after.json"]["containers"][0]["health"] = "unhealthy"
    save()
    with pytest.raises(AssertionError):
        helper.require_operations_inputs(folder, commit, infrastructure_only=True)

"""Classify actual same-source outcomes, receipts and missing tasks; keep failures."""

import ast
import json
from datetime import datetime, timezone

from nas_ssh import ROOT
from stage_nas_production_graphato import COMMIT


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def suite_receipt(folder, engine, pair, suite, target):
    archive = folder / ("leroy-artifacts" if engine == "leroy" else f"jenkins-{pair['jenkins']['number']}-artifacts")
    values = [(path, read(path)) for path in archive.rglob("result.json")]
    selected = [(path, value) for path, value in values if value.get("suite") == suite and "checks" in value]
    if not selected:
        logs = [folder / f"jenkins-{pair['jenkins']['number']}-console.log"] if engine == "jenkins" else list(folder.glob("leroy-*.log"))
        text = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in logs)
        control = target["postdeploy_control_directory"]
        confirmed_probe = control.get("original_marker_validation_error") == "Run markers require root-private directories" and control.get("diagnostic_created_files") is False
        reconstructed = folder.parent / "marker-precondition-reproduction.json"
        reconstructed_probe = False
        if engine == "jenkins" and reconstructed.exists():
            probe = read(reconstructed)
            reconstructed_probe = (probe["captured_target_precondition"] == control
                                   and probe["commit"] == target["manifest"]["commit"]
                                   and probe["application_source_sha256"] == target["manifest"]["files"]["deployments/linux/host/postdeploy.py"]
                                   and probe["original_marker_validation_error"] == "Run markers require root-private directories"
                                   and probe["captured_mode_reproduced"] and probe["temporary_fixture_removed"]
                                   and not probe["actual_application_directory_modified"])
        if "Run markers require root-private directories" in text or ((confirmed_probe or reconstructed_probe) and "CI deployment failed (ValueError)" in text):
            assert control["exists"] and control["is_directory"] and not control["is_symlink"]
            assert control["mode"] != "0o700" or control["uid"] != 0
            return {"receipt_available": False, "startup_failure": "Run markers require root-private directories",
                    "control_directory": control, "checks_executed": 0, "complete_suite_passed": False,
                    "diagnostic_scope": "captured metadata plus unchanged-source temporary reproduction" if reconstructed_probe else "original runtime probe or explicit console error",
                    "diagnostic_evidence": reconstructed.relative_to(ROOT).as_posix() if reconstructed_probe else None}
        return {"receipt_available": False, "startup_failure": None,
                "checks_executed": None, "complete_suite_passed": False,
                "failure_analysis_complete": False}
    (path, receipt), = selected
    for key in ("commit", "runtimeImageId", "sourceSha256", "buildTimestamp"):
        assert receipt[key] == target["receipt"][key], key
    assert receipt["requestedGroup"] == "all" and receipt["reused"] == []
    assert receipt["activeRelease"] and receipt["completedAt"] > receipt["startedAt"]
    checks = {name: {"passed": value["passed"], "exitCode": value["exitCode"]}
              for name, value in receipt["checks"].items()}
    return {"receipt_available": True, "evidence": path.relative_to(ROOT).as_posix(),
            "identity": {key: receipt[key] for key in ("commit", "runtimeImageId", "sourceSha256", "buildTimestamp", "suite", "runId")},
            "checks": checks, "checks_executed": len(checks),
            "passed_groups": sum(value["passed"] for value in checks.values()),
            "failed_groups": sorted(name for name, value in checks.items() if not value["passed"]),
            "cleanup_complete": receipt["cleanupComplete"], "cancelled": receipt["cancelled"],
            "complete_suite_passed": receipt["passed"] and receipt["requestedPassed"]}


def main():
    base = ROOT / "test-results/nas-parity/followup/candidates/graphato" / COMMIT
    staged = read(base / "staged.json")
    assert staged["source_kind"] == "observed_production_revision" and not staged["application_patches_applied"]
    executions = read(base / "current-source-comparison.json")
    assert not executions["receipt_and_failure_analysis_pending"] or not (base / "current-source-analysis.json").exists()
    targets = {engine: read(base / "graphato-ci" / (engine + "-final-state.json")) for engine in ("jenkins", "leroy")}
    delivery = read(base / "graphato-ci/comparison.json")
    assert delivery["comparison_completed"] and delivery["workload_success"] and not delivery["application_patches_applied"]
    checkout = ROOT / ".sources/production-review/graphato-ed21c2e6346a"
    constants = {}
    for node in ast.parse((checkout / "deployments/linux/host/postdeploy.py").read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign):
            for name in node.targets:
                if isinstance(name, ast.Name) and name.id in {"WEB_CASES", "QUALITY_CHECKS"}:
                    constants[name.id] = ast.literal_eval(node.value)
    required = {"web": {"browser-core", *("browser-" + name for name in constants["WEB_CASES"])},
                "quality": set(constants["QUALITY_CHECKS"])}
    suites, pipelines = {}, {}
    for name in ("graphato-bootstrap-host", "graphato-ci", "graphato-release-acceptance", "graphato-postdeploy-web", "graphato-postdeploy-quality"):
        folder = base / name
        pair, run = read(folder / "pair.json"), read(folder / "leroy-run.json")
        assert not pair["application_patches_applied"] and not pair["jenkins"]["building"]
        assert pair["commit"] in pair["jenkins"]["checkout_revisions"] and run["commit"] == pair["commit"]
        assert pair["jenkins"]["result"] in {"SUCCESS", "FAILURE"} and run["status"] in {"succeeded", "failed"}
        successful = pair["jenkins"]["result"] == "SUCCESS" and run["status"] == "succeeded"
        same_terminal = (pair["jenkins"]["result"] == "SUCCESS") == (run["status"] == "succeeded")
        row = {"jenkins_build": pair["jenkins"]["number"], "jenkins_result": pair["jenkins"]["result"],
               "leroy_run": run["id"], "leroy_status": run["status"], "source_matches": True,
               "workload_success_both": successful, "same_terminal_outcome": same_terminal,
               "state": "validated_current_source_scenario" if successful else "execution_difference"}
        if name.startswith("graphato-postdeploy-"):
            suite = name.removeprefix("graphato-postdeploy-")
            receipts = {engine: suite_receipt(folder, engine, pair, suite, targets[engine]) for engine in targets}
            jenkins, leroy = receipts["jenkins"], receipts["leroy"]
            if all(value["receipt_available"] for value in receipts.values()):
                complete = all(set(value["checks"]) == required[suite] and value["cleanup_complete"] and not value["cancelled"] for value in receipts.values())
                same_failure = complete and jenkins["checks"] == leroy["checks"]
                classified_cause = False
            else:
                complete = False
                same_failure = all(value.get("startup_failure") == "Run markers require root-private directories" and value["checks_executed"] == 0 for value in receipts.values())
                classified_cause = same_failure
            row.update(same_check_outcomes_or_startup_failure=same_failure, all_required_groups_executed=complete,
                       same_failure_cause_classified=classified_cause)
            if not successful and same_terminal and same_failure:
                row["state"] = "matching_application_failure" if classified_cause else "matching_failed_checks"
            suites[suite] = {"required_checks": sorted(required[suite]), "engines": receipts,
                             "same_check_outcomes_or_startup_failure": same_failure,
                             "all_required_groups_executed": complete}
        pipelines[name] = row
    release = pipelines["graphato-release-acceptance"]
    if release["same_terminal_outcome"] and release["jenkins_result"] == "FAILURE" and all(
        pipelines["graphato-postdeploy-" + suite]["state"] in {"matching_application_failure", "matching_failed_checks"} for suite in suites
    ):
        release["state"] = "matching_downstream_failure"
        release["note"] = "Beide Release-Jobs melden die belegten Fehler ihrer vollständigen Kindlaufhierarchie."
    preparations = {engine: read(base / (engine + "-vm-preparation.json")) for engine in targets}
    assert preparations["jenkins"]["ready"] == preparations["leroy"]["ready"]
    budget = read(base / "parent-budget-correction.json")
    assert budget["runtime_and_docker_config_matched"] and not budget["additional_swap_allowed"]
    swap = read(base / "original-builder-swap-alignment.json")
    assert swap["runtime_and_docker_config_matched"] and swap["compose_persisted"]
    assert swap["parent_swap_limit_bytes"] == 2 * 1024**3
    assert not swap["original_builder_resource_limits_changed"] and not swap["production_modified"]
    reserve = read(base / "fixture-swap-reserve.json")
    assert reserve["runtime_and_docker_config_matched"] and reserve["compose_persisted"]
    assert reserve["parent_swap_limit_bytes"] == 3 * 1024**3 and reserve["original_builder_swap_limit_bytes"] == 2 * 1024**3
    assert not reserve["original_builder_resource_limits_changed"] and not reserve["production_modified"]
    start_policy_path = base / "graphato-ci/leroy-start-resource-policy.json"
    start_policy = read(start_policy_path)
    assert start_policy["runtime_and_saved_limits_match"] and start_policy["comparison_jenkins_stopped"]
    assert start_policy["memory_bytes"] == 4831838208 and start_policy["parent_swap_limit_bytes"] == reserve["parent_swap_limit_bytes"]
    assert start_policy["job_control_memory_bytes"] == 2 * 1024**3 and start_policy["job_control_swap_limit_bytes"] == 0
    assert not start_policy["production_modified"] and not start_policy["identical_jenkins_starting_conditions_asserted"]
    record = {"at": datetime.now(timezone.utc).isoformat(), "commit": COMMIT, "application_patches_applied": False,
              "pipelines": pipelines, "suites": suites, "delivery_evidence": (base / "graphato-ci/comparison.json").relative_to(ROOT).as_posix(),
              "fresh_target_per_engine": True, "same_guest_package_and_network_policy": True,
              "parent_budget_evidence": (base / "parent-budget-correction.json").relative_to(ROOT).as_posix(),
              "current_swap_budget_evidence": (base / "fixture-swap-reserve.json").relative_to(ROOT).as_posix(),
              "current_parent_swap_limit_bytes": reserve["parent_swap_limit_bytes"],
              "original_builder_swap_limit_bytes": reserve["original_builder_swap_limit_bytes"],
              "leroy_start_resource_evidence": start_policy_path.relative_to(ROOT).as_posix(),
              "identical_starting_resource_conditions_asserted": False, "performance_comparison_valid": False,
              "workload_success_both": all(row["workload_success_both"] for row in pipelines.values()),
              "all_failures_classified": all(row["state"] not in {"execution_difference", "matching_failed_checks"} for row in pipelines.values()),
              "production_modified": False, "production_cutover": False, "production_replacement_ready": False}
    (base / "current-source-analysis.json").write_text(json.dumps(record, indent=2) + "\n")
    executions["receipt_and_failure_analysis_pending"] = False
    executions["failure_cause_analysis_pending"] = not record["all_failures_classified"]
    executions["analysis_evidence"] = (base / "current-source-analysis.json").relative_to(ROOT).as_posix()
    (base / "current-source-comparison.json").write_text(json.dumps(executions, indent=2) + "\n")
    print(json.dumps({"commit": COMMIT, "states": {name: row["state"] for name, row in pipelines.items()},
                      "workload_success_both": record["workload_success_both"]}))


if __name__ == "__main__":
    main()

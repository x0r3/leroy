"""Analyze fresh frozen-master deliveries without promoting absent suite results."""

import argparse
import ast
import json
from datetime import datetime, timezone

from analyze_current_nas_graphato import suite_receipt
from nas_candidate_paths import candidate_checkout
from nas_ssh import ROOT


def read(path):
    return json.loads(path.read_text())


def observations(path):
    assert path.stat().st_size < 8 * 1024**2
    # The periodic observer may be appending its next sample during analysis.
    data = path.read_bytes()
    lines = data[:data.rfind(b"\n") + 1].splitlines()
    rows = [json.loads(line) for line in lines]
    assert rows and all(row["read_only"] for row in rows)
    return rows


def sampled_runtime(base, run_id):
    control_path = base / "control-plane-observations.jsonl"
    control = observations(control_path)
    assert all(set(row["services"]) == {"controller", "postgres", "runner"} for row in control)
    services = [service for row in control for service in row["services"].values()]
    pressure_path = base / "nas-pressure-observations.jsonl"
    pressure = [row for row in observations(pressure_path) if row.get("job_control", {}).get("run") == run_id]
    assert pressure
    heartbeats = [row["sampled_heartbeats"] for row in pressure if row.get("sampled_heartbeats")]
    controls = [row["job_control"] for row in pressure if row["job_control"].get("runtime_cgroup_available")]
    diagnostics = {(value["at"], value["diagnostic"]) for row in pressure
                   for value in row["job_control"].get("lease_diagnostics", [])}
    return {"control_plane": {
                "evidence": control_path.relative_to(ROOT).as_posix(), "samples": len(control),
                "first_at": control[0]["at"], "last_at": control[-1]["at"],
                "swap_zero_at_all_samples": all(row["swap_current_bytes"] == row["swap_max_bytes"] == 0 for row in services),
                "no_oom_or_restart_observed": all(not row["oom_killed"] and row["restart_count"] == 0
                    and int(row["memory_events"]["oom"]) == int(row["memory_events"]["oom_kill"]) == 0 for row in services)},
            "build_control": {
                "evidence": pressure_path.relative_to(ROOT).as_posix(), "run": run_id, "samples": len(pressure),
                "first_at": pressure[0]["at"], "last_at": pressure[-1]["at"],
                "available_cgroup_samples": len(controls),
                "job_control_swap_zero_at_available_samples": bool(controls) and all(
                    int(row["memory.swap.current"]) == int(row["memory.swap.max"]) == 0 for row in controls),
                "heartbeat_samples": len(heartbeats),
                "largest_observed_heartbeat_gap_seconds": max(
                    (row["largest_observed_gap_seconds"] for row in heartbeats), default=None),
                "all_sampled_heartbeat_http_success": bool(heartbeats) and all(row["all_http_success"] for row in heartbeats),
                "distinct_lease_renewal_diagnostics": len(diagnostics),
                "transient_api_timeouts_observed": any("ReadTimeout" in message for _, message in diagnostics)},
            "every_instant_observed": False, "performance_comparison": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    commit = args.commit
    base = ROOT / "test-results/nas-parity/followup/candidates/graphato" / commit
    staged = read(base / "staged.json")
    assert staged["source_kind"] == "frozen_master_revision" and not staged["application_patches_applied"]
    execution = read(base / "current-source-comparison.json")
    activity_path = base / "production-activity-audit.json"
    if not activity_path.exists():
        from audit_nas_production_activity import collect_activity

        activity = collect_activity(read(base / "production-jobs-before.json")["jobs"],
                                    read(base / "production-jobs-after.json")["jobs"])
        activity_path.write_text(json.dumps(activity, indent=2) + "\n")
    activity = read(activity_path)
    assert activity["read_only"] and not activity["production_modified_by_agent"]
    assert not activity["production_builds_triggered_by_this_task"]
    assert activity["original_counters_unchanged"] == execution["production_jobs_unchanged"]
    assert execution["production_jobs_unchanged"] or activity["all_changed_builds_have_recognized_trigger_causes"]
    delivery = read(base / "graphato-ci/comparison.json")
    assert delivery["comparison_completed"] and delivery["workload_success"]
    budget_path = base / "graphato-ci/leroy-start-resource-policy.json"
    budget = read(budget_path)
    assert budget["runtime_and_saved_limits_match"] and budget["comparison_jenkins_stopped"]
    assert budget["memory_bytes"] == 4831838208 and budget["parent_swap_limit_bytes"] == 3 * 1024**3
    assert budget["job_control_memory_bytes"] == 2 * 1024**3 and budget["job_control_swap_limit_bytes"] == 0
    assert not budget["production_modified"] and not budget["identical_jenkins_starting_conditions_asserted"]
    targets = {engine: read(base / "graphato-ci" / (engine + "-final-state.json")) for engine in ("jenkins", "leroy")}
    constants = {}
    for node in ast.parse((candidate_checkout(commit) / "deployments/linux/host/postdeploy.py").read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign):
            for name in node.targets:
                if isinstance(name, ast.Name) and name.id in {"WEB_CASES", "QUALITY_CHECKS"}:
                    constants[name.id] = ast.literal_eval(node.value)
    required = {"web": {"browser-core", *("browser-" + name for name in constants["WEB_CASES"])},
                "quality": set(constants["QUALITY_CHECKS"])}
    pipelines, suites = {}, {}
    for name in ("graphato-bootstrap-host", "graphato-ci", "graphato-release-acceptance", "graphato-postdeploy-web", "graphato-postdeploy-quality"):
        folder = base / name
        pair, run = read(folder / "pair.json"), read(folder / "leroy-run.json")
        assert pair["commit"] in pair["jenkins"]["checkout_revisions"] and run["commit"] == pair["commit"]
        assert not pair["application_patches_applied"] and not pair["jenkins"]["building"]
        assert pair["jenkins"]["result"] in {"SUCCESS", "FAILURE"} and run["status"] in {"succeeded", "failed"}
        success = pair["jenkins"]["result"] == "SUCCESS" and run["status"] == "succeeded"
        row = {"jenkins_build": pair["jenkins"]["number"], "jenkins_result": pair["jenkins"]["result"],
               "leroy_run": run["id"], "leroy_status": run["status"], "source_matches": True,
               "same_terminal_outcome": (pair["jenkins"]["result"] == "SUCCESS") == (run["status"] == "succeeded"),
               "workload_success_both": success, "state": "validated_current_source_scenario" if success else "execution_difference"}
        if name.startswith("graphato-postdeploy-"):
            suite = name.removeprefix("graphato-postdeploy-")
            receipts = {engine: suite_receipt(folder, engine, pair, suite, target) for engine, target in targets.items()}
            complete = all(value["receipt_available"] and set(value["checks"]) == required[suite]
                           and value["cleanup_complete"] and not value["cancelled"] for value in receipts.values())
            same = complete and receipts["jenkins"]["checks"] == receipts["leroy"]["checks"]
            same_startup = all(not value["receipt_available"] and value.get("startup_failure") == "Run markers require root-private directories"
                               and value["checks_executed"] == 0 for value in receipts.values())
            if not success and (same or same_startup):
                row["state"] = "matching_application_failure" if same_startup else "matching_failed_checks"
            suites[suite] = {"required_checks": sorted(required[suite]), "engines": receipts,
                             "all_required_groups_executed": complete, "same_check_outcomes_or_startup_failure": same or same_startup}
            row.update(all_required_groups_executed=complete,
                       same_check_outcomes_or_startup_failure=same or same_startup,
                       same_failure_cause_classified=same_startup)
        pipelines[name] = row
    parent = pipelines["graphato-release-acceptance"]
    if parent["jenkins_result"] == "FAILURE" and parent["leroy_status"] == "failed" and all(
        pipelines["graphato-postdeploy-" + suite]["state"] in {"matching_application_failure", "matching_failed_checks"} for suite in suites
    ):
        parent["state"] = "matching_downstream_failure"
    preparations = {engine: read(base / (engine + "-vm-preparation.json")) for engine in targets}
    assert preparations["jenkins"]["ready"] == preparations["leroy"]["ready"]
    record = {"at": datetime.now(timezone.utc).isoformat(), "commit": commit, "application_patches_applied": False,
              "source_kind": "frozen_master_revision", "pipelines": pipelines, "suites": suites,
              "leroy_start_resource_evidence": budget_path.relative_to(ROOT).as_posix(),
              "fresh_target_per_engine": True, "same_guest_package_and_network_policy": True,
              "workload_success_both": all(row["workload_success_both"] for row in pipelines.values()),
              "all_failures_classified": all(row["state"] not in {"execution_difference", "matching_failed_checks"} for row in pipelines.values()),
              "production_job_counters_unchanged": execution["production_jobs_unchanged"],
              "production_activity_audit": activity_path.relative_to(ROOT).as_posix(),
              "production_modified": False, "production_cutover": False, "production_replacement_ready": False,
              "performance_comparison": False}
    record["sampled_runtime"] = sampled_runtime(base, pipelines["graphato-ci"]["leroy_run"])
    (base / "current-source-analysis.json").write_text(json.dumps(record, indent=2) + "\n")
    execution.update(receipt_and_failure_analysis_pending=False,
                     analysis_evidence=(base / "current-source-analysis.json").relative_to(ROOT).as_posix())
    (base / "current-source-comparison.json").write_text(json.dumps(execution, indent=2) + "\n")
    print(json.dumps({"commit": commit, "states": {name: row["state"] for name, row in pipelines.items()},
                      "workload_success_both": record["workload_success_both"]}), flush=True)


if __name__ == "__main__":
    main()

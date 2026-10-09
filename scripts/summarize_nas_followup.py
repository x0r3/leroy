"""Record completed follow-up evidence without rewriting the original comparison."""

import argparse
import json
import re
from datetime import datetime, timezone

from nas_ssh import ROOT
from stage_nas_production_graphato import COMMIT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graphato-commit", help="Include a completed explicit frozen-master acceptance separately")
    args = parser.parse_args()
    base = ROOT / "test-results/nas-parity/followup"
    current = base / "candidates/graphato" / COMMIT
    reports = {
        "ssh_transport": base / "ssh-acceptance-after-pressure/report.json",
        "lifecycle": base / "nas-lifecycle/state.json",
        "backup_restore": base / "nas-backup/report.json",
        "full_stack_restart": base / "nas-stack-restart/report.json",
        "recovered_services": base / "nas-stack-services/run.json",
        "parallel_workers": base / "nas-parallel/state.json",
        "home_lab_build": base / "home-lab-build/comparison.json",
        "ui": base.parent / "visual-followup-ops/report.json",
        "ui_followup_results": base.parent / "visual-followup-results/report.json",
        "ui_graphato_live": base.parent / "visual-graphato-78e92e09fa5f-live/report.json",
        "ui_graphato_candidate": base.parent / "visual-graphato-78e92e09fa5f/report.json",
        "ui_graphato_rate_limit_candidate": base.parent / "visual-graphato-9968c226f943/report.json",
        "artifact_concurrency_local": base / "artifact-concurrency-tests.json",
        "artifact_concurrency_deployed": base / "artifact-concurrency-deployment.json",
        "ui_graph_focus_local": base.parent / "visual-graph-focus-production/report.json",
        "ui_graph_focus_nas": base.parent / "visual-graph-focus/report.json",
        "ui_antares_timeout": base.parent / "visual-antares-cpu2-timeout/report.json",
        "ui_log_heartbeat": base.parent / "visual-log-heartbeat/report.json",
        "ui_interrupted": base.parent / "visual-interrupted-status/report.json",
        "ui_timeline_deployed": base.parent / "timeline-status-ui.json",
        "cancel_cleanup_nas": base / "cancel-cleanup-tcp-ready/report.json",
        "postgres_readiness_local": base / "antares-database-readiness/after.json",
        "runner_nested_cleanup_local": base / "runner-nested-cleanup/local.json",
        "runner_nested_cleanup_nas": base / "runner-nested-cleanup/nas.json",
        "ui_cancel_cleanup": base.parent / "visual-cancel-cleanup/report.json",
        "antares_buildx": base / "antares-buildx/applied.json",
        "log_heartbeat_local": base / "log-heartbeat-tests.json",
        "log_heartbeat_deployed": base / "log-heartbeat-deployment.json",
        "log_heartbeat_nas": base / "log-heartbeat-under-load/report.json",
        "linux_pool_preflight": base / "linux-pool/preflight.json",
        "ui_linux_pool": base.parent / "visual-linux-pool/report.json",
        "linux_pool_complete_pair": base / "linux-pool/complete-pair.json",
        "ui_antares_complete": base.parent / "visual-antares-3afb3b4f534448779cfa7dca15593147/report.json",
        "production_source_review": base / "production-source-review/review.json",
        "newer_graphato_pipeline_contract": base / "production-source-review/newer-pipeline-contract.json",
        "nas_only_scope": base / "production-source-review/nas-only-scope.json",
        "ui_nas_scope": base.parent / "visual-nas-scope-after-budget-relief-v2/report.json",
        "ui_nas_scope_after_reserve": base.parent / "visual-nas-scope-after-fixture-reserve/report.json",
        "nas_fixture_budget": base / "candidates/graphato/ed21c2e6346aab6f71494765a37ba91e0d4559b7/parent-budget-correction.json",
        "nas_original_builder_swap": base / "candidates/graphato/ed21c2e6346aab6f71494765a37ba91e0d4559b7/original-builder-swap-alignment.json",
        "nas_fixture_swap_reserve": base / "candidates/graphato/ed21c2e6346aab6f71494765a37ba91e0d4559b7/fixture-swap-reserve.json",
        "nas_fixture_compose_validation": base / "candidates/graphato/ed21c2e6346aab6f71494765a37ba91e0d4559b7/compose-budget-validation.json",
        "production_quality_failure_diagnosis": base / "production-source-review/failed-groups/failure-signatures.json",
        "production_merge_failure_observation": base / "production-source-review/failed-groups/browser-merge-observation.json",
        "original_quality_test_evidence": base / "production-source-review/failed-groups/original-quality-test-evidence.json",
        "control_residency_tests": current / "control-residency-tests.json",
        "control_residency_deployment": current / "control-residency-deployment.json",
        "control_residency_original_workload": current / "control-residency-workload.json",
        "control_plane_residency": base / "control-plane-residency-deployment.json",
        "control_plane_real_workload": base / "control-plane-residency-workload/report.json",
        "control_plane_full_workload": current / "scenarios/root-private-existing-host/analysis.json",
        "marker_precondition_reproduction": current / "marker-precondition-reproduction.json",
        "ui_current_graphato_interrupted": base.parent / "visual-graphato-ed21c2e6346a-interrupted-4123408f/report.json",
        "graphato_current_source_analysis": current / "current-source-analysis.json",
        "graphato_original_full_suite_comparison": current / "scenarios/root-private-existing-host/analysis.json",
        "ui_current_graphato_fresh": base.parent / "visual-graphato-ed21c2e6346a/report.json",
        "ui_current_graphato_existing_host": base.parent / "visual-graphato-ed21c2e6346a-existing-host/report.json",
        "child_failure_reason_tests": base / "child-failure-reason-tests.json",
        "child_failure_reason_deployment": base / "child-failure-reason-deployment.json",
        "child_failure_reason_nas": base / "child-failure-reason-nas/report.json",
        "ui_child_failure_reason": base.parent / "visual-child-failure-reason/report.json",
    }
    checks = {}
    for name, path in reports.items():
        if not path.exists():
            checks[name] = {"passed": False, "state": "not_yet_recorded"}
            continue
        data = json.loads(path.read_text())
        passed = {
            "ssh_transport": data.get("transport_regression_passed", False),
            "lifecycle": data.get("passed", False),
            "backup_restore": data.get("passed", False),
            "full_stack_restart": data.get("passed", False),
            "recovered_services": data.get("status") == "succeeded",
            "parallel_workers": data.get("workload_passed", False)
            and data.get("original_capacity_and_profiles_restored", False),
            "home_lab_build": data.get("workload_success_both", False)
            and data.get("observed_scenario_parity", False),
            "ui": data.get("passed", False) and data.get("manual_visual_review", False),
            "ui_followup_results": data.get("passed", False) and data.get("manual_visual_review", False),
            "ui_graphato_live": data.get("passed", False) and data.get("manual_visual_review", False),
            "ui_graphato_candidate": data.get("passed", False) and data.get("manual_visual_review", False),
            "ui_graphato_rate_limit_candidate": data.get("passed", False)
            and data.get("manual_visual_review", False),
            "artifact_concurrency_local": data.get("passed", False) and data.get("postgresql_real", False),
            "artifact_concurrency_deployed": data.get("readiness", False),
            "ui_graph_focus_local": data.get("passed", False) and data.get("manual_visual_review", False),
            "ui_graph_focus_nas": data.get("passed", False) and data.get("manual_visual_review", False),
            "ui_antares_timeout": data.get("passed", False) and data.get("manual_visual_review", False),
            "ui_log_heartbeat": data.get("passed", False) and data.get("manual_visual_review", False),
            "ui_interrupted": data.get("passed", False) and data.get("manual_visual_review", False),
            "ui_timeline_deployed": data.get("served_assets_verified", False),
            "cancel_cleanup_nas": data.get("passed", False) and data.get("final_status") == "timed_out",
            "postgres_readiness_local": data.get("tcp_ready_after_action", False),
            "runner_nested_cleanup_local": data.get("passed", False) and data.get("unrelated_container_preserved", False),
            "runner_nested_cleanup_nas": data.get("passed", False) and data.get("nested_helper_removed", False),
            "ui_cancel_cleanup": data.get("passed", False) and data.get("manual_visual_review", False),
            "antares_buildx": data.get("same_binary", False)
            and all(data.get("engines", {}).get(engine, {}).get("build_succeeded", False)
                    for engine in ("jenkins", "leroy")),
            "log_heartbeat_local": data.get("passed", False) and data.get("postgresql_real", False),
            "log_heartbeat_deployed": data.get("readiness", False),
            "log_heartbeat_nas": data.get("passed", False) and data.get("messages") == 120,
            "linux_pool_preflight": data.get("passed", False) and data.get("controller_reachable", False)
            and data.get("blocked_nas_ports") == [22, 9000, 9443],
            "ui_linux_pool": data.get("passed", False) and data.get("manual_visual_review", False),
            "linux_pool_complete_pair": data.get("passed", False)
            and data.get("workload_success_both", False)
            and data.get("job_and_nested_helpers_removed", False)
            and data.get("job_work_volume_removed", False)
            and data.get("production_jobs_unchanged", False),
            "ui_antares_complete": data.get("passed", False) and data.get("manual_visual_review", False),
            "production_source_review": data.get("read_only", False) and len(data.get("pipelines", [])) == 13
            and data.get("included_pipeline_count") == 12,
            "newer_graphato_pipeline_contract": data.get("read_only", False)
            and len(data.get("newer_revisions", [])) == 2
            and all(row.get("jenkinsfiles_identical", False) for row in data.get("newer_revisions", []))
            and not data.get("newer_workload_parity_claimed", True),
            "nas_only_scope": data.get("user_authorized_exclusion", False)
            and data.get("optional_local_linux_pool_stopped", False) and data.get("production_jobs_unchanged", False),
            "ui_nas_scope": data.get("passed", False) and data.get("manual_visual_review", False)
            and data.get("antares_excluded", False) and not data.get("workload_acceptance_asserted", True),
            "ui_nas_scope_after_reserve": data.get("passed", False) and data.get("manual_visual_review", False)
            and data.get("nas_worker_online", False) and not data.get("optional_pool_online", True)
            and data.get("antares_excluded", False) and not data.get("workload_acceptance_asserted", True),
            "nas_fixture_budget": data.get("runtime_and_docker_config_matched", False)
            and data.get("compose_persisted", False) and not data.get("additional_swap_allowed", True)
            and not data.get("production_modified", True),
            "nas_original_builder_swap": data.get("runtime_and_docker_config_matched", False)
            and data.get("compose_persisted", False) and data.get("parent_swap_limit_bytes") == 2 * 1024**3
            and not data.get("original_builder_resource_limits_changed", True)
            and not data.get("production_modified", True),
            "nas_fixture_swap_reserve": data.get("runtime_and_docker_config_matched", False)
            and data.get("compose_persisted", False) and data.get("parent_swap_limit_bytes") == 3 * 1024**3
            and data.get("original_builder_swap_limit_bytes") == 2 * 1024**3
            and not data.get("original_builder_resource_limits_changed", True)
            and not data.get("production_modified", True),
            "nas_fixture_compose_validation": data.get("runtime_and_saved_limits_match", False)
            and data.get("read_only", False) and not data.get("services_recreated", True)
            and not data.get("production_modified", True),
            "production_quality_failure_diagnosis": data.get("quality", {}).get("cause_reproduced", False)
            and not data.get("full_pipeline_acceptance", True)
            and not data.get("application_patches_applied", True) and not data.get("production_modified", True),
            "production_merge_failure_observation": data.get("read_only", False)
            and data.get("business_cause_classified") is False and bool(data.get("visible_error"))
            and not data.get("application_patches_applied", True) and not data.get("production_modified", True),
            "original_quality_test_evidence": data.get("read_only", False)
            and data.get("test_results", {}).get("rust", {}).get("ok") == 1579
            and not data.get("production_modified", True),
            "control_residency_tests": data.get("passed", False) and data.get("postgresql_real", False),
            "control_residency_deployment": data.get("graphato_job_swap_limit_bytes") == 0
            and data.get("lease_seconds_unchanged") == 90 and len(data.get("images", {})) == 3
            and not data.get("application_patches_applied", True) and not data.get("production_modified", True),
            "control_residency_original_workload": data.get("tested_workload_completed_after_control_policy_change", False)
            and data.get("all_ci_steps_successful", False) and data.get("job_swap_observed_zero", False)
            and data.get("lease_seconds_unchanged") == 90 and not data.get("application_patches_applied", True),
            "control_plane_residency": data.get("code_images_match_previously_deployed_versions", False)
            and data.get("lease_seconds_unchanged") == 90 and data.get("worker_confirmation_seconds_unchanged") == 45
            and all(row.get("swap_current_bytes") == 0 for row in data.get("services", {}).values())
            and len(data.get("services", {})) == 3 and not data.get("production_modified", True),
            "control_plane_real_workload": data.get("passed", False) and data.get("duration_at_least_240_seconds", False)
            and data.get("worker_lease_budget_unchanged", False) and not data.get("full_graphato_comparison", True),
            "control_plane_full_workload": data.get("all_required_groups_executed_both", False)
            and data.get("no_migration_execution_difference_observed", False)
            and data.get("sampled_control_plane", {}).get("swap_zero_at_all_samples", False)
            and data.get("sampled_control_plane", {}).get("no_oom_or_restart_observed", False)
            and not data.get("application_patches_applied", True),
            "marker_precondition_reproduction": data.get("captured_mode_reproduced", False)
            and data.get("root_private_mode_accepts_marker_path", False)
            and data.get("temporary_fixture_removed", False) and not data.get("actual_application_directory_modified", True),
            "ui_current_graphato_interrupted": data.get("passed", False) and data.get("manual_visual_review", False),
            "graphato_current_source_analysis": data.get("all_failures_classified", False)
            and data.get("fresh_target_per_engine", False) and not data.get("application_patches_applied", True),
            "graphato_original_full_suite_comparison": data.get("all_required_groups_executed_both", False)
            and data.get("no_migration_execution_difference_observed", False)
            and not data.get("application_patches_applied", True) and not data.get("production_modified", True),
            "ui_current_graphato_fresh": data.get("passed", False) and data.get("manual_visual_review", False),
            "ui_current_graphato_existing_host": data.get("passed", False) and data.get("manual_visual_review", False),
            "child_failure_reason_tests": data.get("passed", False) and data.get("postgresql_real", False)
            and '102 passed' in data.get("output", ""),
            "child_failure_reason_deployment": len(data.get("images", {})) == 2
            and data.get("profiles_unchanged", False) and data.get("controller_and_runner_not_restarted", False)
            and not data.get("production_modified", True),
            "child_failure_reason_nas": data.get("passed", False) and data.get("both_runs_remain_failed", False)
            and data.get("job_containers_removed", False)
            and (data.get("production_jobs_unchanged", False) or data.get("independent_production_activity_audited", False)),
            "ui_child_failure_reason": data.get("passed", False) and data.get("manual_visual_review", False)
            and data.get("parent_reason_visible", False) and data.get("both_runs_remain_failed", False),
        }[name]
        checks[name] = {"passed": passed, "evidence": str(path.relative_to(ROOT)).replace("\\", "/")}
    candidates = []
    for path in sorted((base / "candidates").glob("*/*/staged.json")):
        staged = json.loads(path.read_text())
        comparison = path.with_name("comparison.json")
        result = json.loads(comparison.read_text()) if comparison.exists() else {}
        candidates.append(
            {
                "repository": staged["repository"],
                "commit": staged["commit"],
                "original_commit": staged["original_commit"],
                "patch": staged["patch"],
                "source_kind": staged.get("source_kind", "separate_application_candidate"),
                "application_patches_applied": staged.get("application_patches_applied", bool(staged["patch"])),
                "workload_success_both": result.get("workload_success_both", False),
                "comparison": str(comparison.relative_to(ROOT)).replace("\\", "/")
                if comparison.exists()
                else None,
                "execution_host": result.get("execution_pool", {}).get("execution_host", "NAS test daemon"),
            }
        )
    record = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "candidates": candidates,
        "production_replacement_ready": False,
        "scope": "Additional NAS evidence; original failures remain preserved",
    }
    record["current_original_graphato"] = {
        "commit": COMMIT, "application_patches_applied": False,
        "fresh_comparison_evidence": reports["graphato_current_source_analysis"].relative_to(ROOT).as_posix(),
        "prepared_host_comparison_evidence": reports["graphato_original_full_suite_comparison"].relative_to(ROOT).as_posix(),
        "successful_followup_checks_mean_successful_pipelines": False,
        "scope": "Comparison and diagnosis checks are separate from successful application workloads",
    }
    for key, filename in (("fresh_target", "current-source-analysis.json"),
                          ("prepared_host", "scenarios/root-private-existing-host/analysis.json")):
        path = current / filename
        if path.exists():
            result = json.loads(path.read_text())
            record["current_original_graphato"][key] = {
                "workload_success_both": result["workload_success_both"],
                "pipelines": result["pipelines"], "suites": result["suites"],
            }
    scope_path = base / "production-source-review/nas-only-scope.json"
    if scope_path.exists():
        record["accepted_scope"] = json.loads(scope_path.read_text())
        record["accepted_scope"]["evidence"] = scope_path.relative_to(ROOT).as_posix()
        review_path = scope_path.with_name("review.json")
        record["production_source_review"] = {
            "evidence": review_path.relative_to(ROOT).as_posix(),
            "scope": "Application patches are separate; Antares original unit/integration budgets differ from its successful candidate",
            "same_candidate_success_is_current_source_acceptance": False,
        }
    newer_path = base / "production-source-review/newer-pipeline-contract.json"
    if newer_path.exists():
        reviewed = json.loads(newer_path.read_text())
        assert reviewed["read_only"] and not reviewed["newer_workload_parity_claimed"]
        record["newer_production_graphato_contract_review"] = {
            "observed_at": reviewed["at"],
            "evidence": newer_path.relative_to(ROOT).as_posix(),
            "frozen_comparison_commit": reviewed["frozen_comparison_commit"],
            "revisions": [{"commit": row["commit"],
                           "jenkinsfiles_identical": row["jenkinsfiles_identical"],
                           "changed_selected_helpers": [file["path"] for file in row["reviewed_files"]
                                                        if not file["identical"]]}
                          for row in reviewed["newer_revisions"]],
            "newer_workload_parity_claimed": False,
            "scope": "Read-only source review of later production commits; earlier observed production receipts retain their recorded revisions and timestamps",
        }
    production = sorted(base.glob("production-graphato-failures-*.json"))
    if production:
        path = production[-1]
        observed = json.loads(path.read_text())
        revisions = observed["jobs"]["graphato-ci"]["checkout_revisions"]
        assert len(revisions) == 1 and observed["read_only"]
        failures = {}
        for pipeline in ("graphato-postdeploy-web", "graphato-postdeploy-quality"):
            (receipt,) = [row for row in observed["jobs"][pipeline]["results"] if row.get("suite")]
            assert receipt["commit"] == revisions[0]
            failures[pipeline] = [name for name, result in receipt["checks"].items() if not result["passed"]]
        record["production_graphato_observation"] = {
            "commit": revisions[0], "read_only": True,
            "evidence": path.relative_to(ROOT).as_posix(),
            "failed_groups": failures,
            "candidate_comparison": False,
            "scope": "A different production revision; not covered by the frozen candidate comparison",
        }
    progress = sorted(base.glob("production-graphato-progress-*.json"))
    if progress:
        path = progress[-1]
        observed = json.loads(path.read_text())
        assert observed["read_only"]
        if "jobs" in observed:
            record["latest_production_graphato_progress"] = {
                "observed_at": observed["observed_at"],
                "read_only": True,
                "jobs": observed["jobs"],
                "evidence": path.relative_to(ROOT).as_posix(),
                "scope": "Build progress only; no inferred source revision or full release acceptance",
            }
    for suite in ("web", "quality"):
        receipts = list(base.glob("production-graphato-" + suite + "-*.json"))
        if not receipts:
            continue
        path = max(receipts, key=lambda item: int(item.stem.rsplit("-", 1)[1]))
        observed = json.loads(path.read_text())
        assert observed["read_only"] and observed["job"] == "graphato-postdeploy-" + suite
        if observed.get("receipt_available"):
            record["latest_production_graphato_" + suite] = {
                "observed_at": observed["observed_at"], "read_only": True,
                "number": observed["number"], "result": observed["result"],
                "commit": observed["commit"],
                "passed_groups": sum(row["passed"] for row in observed["checks"].values()),
                "total_groups": len(observed["checks"]),
                "failed_groups": [name for name, row in observed["checks"].items() if not row["passed"]],
                "evidence": path.relative_to(ROOT).as_posix(),
                "candidate_comparison": False,
                "scope": "Production " + suite + " evidence for its recorded revision; not full release acceptance",
            }
    pool = base / "linux-pool/pool.json"
    if pool.exists():
        data = json.loads(pool.read_text())
        assert not data["production_modified"] and data["controller"] == "http://192.168.178.97:8088"
        comparison = base / "candidates/antares" / data["candidate"] / "comparison.json"
        candidate = json.loads(comparison.read_text()) if comparison.exists() else {}
        complete = candidate.get("workload_success_both", False) and candidate.get("complete_matching_gates", False)
        if complete:
            assert candidate["execution_pool"] == data
        final_path = base / "linux-pool/complete-pair.json"
        final = json.loads(final_path.read_text()) if final_path.exists() else {}
        complete = complete and final.get("passed", False) and final.get("full_ci_acceptance", False)
        if complete:
            assert final["candidate"] == data["candidate"] and final["leroy_run"] == candidate["leroy_run"]
        record["dedicated_linux_execution_pool"] = {
            "evidence": pool.relative_to(ROOT).as_posix(), "execution_host": data["execution_host"],
            "controller": data["controller"], "candidate": data["candidate"],
            "profile": data["profile"], "full_ci_acceptance": complete,
            "complete_pair_evidence": final_path.relative_to(ROOT).as_posix() if final_path.exists() else None,
            "scope": "Distributed execution; not evidence that NAS hardware can run the browser workload alone",
            "required_for_current_nas_acceptance": not scope_path.exists(),
            "historical_test_pool_stopped": bool(record.get("accepted_scope", {}).get("optional_local_linux_pool_stopped")),
        }
    if args.graphato_commit:
        assert re.fullmatch(r"[a-f0-9]{40}", args.graphato_commit)
        master = base / "candidates/graphato" / args.graphato_commit
        frozen = json.loads((master / "frozen-master.json").read_text())
        complete = json.loads((master / "master-acceptance-complete.json").read_text())
        assert frozen["commit"] == complete["commit"] == args.graphato_commit
        assert not frozen["application_patches_applied"]
        fresh = json.loads((master / "current-source-analysis.json").read_text())
        prepared = json.loads((master / "scenarios/root-private-existing-host/analysis.json").read_text())
        operations_path = master / "final-operations-acceptance.json"
        operations = json.loads(operations_path.read_text()) if operations_path.exists() else {}
        views = []
        for suffix in ("", "-existing-host"):
            report_path = base.parent / ("visual-graphato-" + args.graphato_commit[:12] + suffix) / "report.json"
            visual = json.loads(report_path.read_text()) if report_path.exists() else {}
            views.append({"evidence": report_path.relative_to(ROOT).as_posix(),
                          "passed": visual.get("passed", False) and visual.get("manual_visual_review", False),
                          "reviewed_views": len(visual.get("reviewed_screenshot_sha256", {})),
                          "verified_artifact_downloads": len(visual.get("artifacts", []))})
        supporting = {}
        for name, relative in {
            "rust_direct_failure": "scenarios/root-private-existing-host/rust-retry-coverage-failure-analysis.json",
            "rust_single_case_probe": "scenarios/root-private-existing-host/rust-retry-coverage-probe.json",
            "infrastructure_scope_tests": "infrastructure-scope-tests.json",
            "quality_parser_tests": "quality-parser-failed-rust-tests.json",
            "acceptance_reporting_tests": "acceptance-reporting-tests.json",
            "image_restore_storage_diagnosis": "release-image-restore-storage-analysis.json",
            "acceptance_helper_tests_final": "acceptance-helper-tests-final.json",
            "image_restore_wait_failure": "release-image-restore-wait-failure.json",
            "restart_idle_builder_drain": "restart-builder-drain.json",
            "frozen_source_integrity_tests": "frozen-integrity-tests.json",
        }.items():
            path = master / relative
            if path.exists():
                supporting[name] = {"evidence": path.relative_to(ROOT).as_posix(),
                                    "result": json.loads(path.read_text())}
        record["frozen_master_graphato"] = {
            "commit": args.graphato_commit, "application_patches_applied": False,
            "source_evidence": (master / "frozen-master.json").relative_to(ROOT).as_posix(),
            "fresh_target": {"workload_success_both": fresh["workload_success_both"],
                             "pipelines": fresh["pipelines"], "suites": fresh["suites"],
                             "evidence": (master / "current-source-analysis.json").relative_to(ROOT).as_posix()},
            "prepared_host": {"workload_success_both": prepared["workload_success_both"],
                              "all_required_groups_executed_both": prepared["all_required_groups_executed_both"],
                              "no_migration_execution_difference_observed": prepared["no_migration_execution_difference_observed"],
                              "pipelines": prepared["pipelines"], "suites": prepared["suites"],
                              "evidence": (master / "scenarios/root-private-existing-host/analysis.json").relative_to(ROOT).as_posix()},
            "ui_reviews": views, "final_operations_passed": operations.get("passed", False),
            "final_operations_scope": operations.get("acceptance_scope"),
            "supporting_diagnosis": supporting,
            "supporting_probe_replaces_full_comparison": False,
            "final_operations_evidence": operations_path.relative_to(ROOT).as_posix() if operations else None,
            "production_configuration_activated": False, "production_credentials_migrated": False,
            "scope": "Explicit frozen master; prior original-source and patched-candidate evidence remains separate",
        }
        previous = master / "acceptance-before-frozen-master"
        previous.mkdir(exist_ok=True)
        for source in (base / "summary.json", ROOT / "docs/acceptance.json"):
            destination = previous / source.name
            if source.exists() and not destination.exists():
                destination.write_bytes(source.read_bytes())
    path = ROOT / "docs/acceptance.json"
    acceptance = json.loads(path.read_text())
    acceptance["scope"] = (
        "Historical local technical acceptance of all 13 migrated jobs on isolated targets, "
        "using the explicitly identified application repair revisions. The top-level complete "
        "flag describes that local run only. Current NAS comparison evidence and readiness "
        "are recorded separately in original_revision_nas_parity and nas_followup. "
        "Production cutover is not performed."
    )
    acceptance["nas_followup"] = record
    path.write_text(json.dumps(acceptance, indent=2) + "\n")
    (base / "summary.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({name: row["passed"] for name, row in checks.items()}))


if __name__ == "__main__":
    main()

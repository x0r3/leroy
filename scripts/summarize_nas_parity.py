"""Summarize observed aligned comparisons without treating skipped work as passed."""

import json
import re
from datetime import datetime, timezone

from nas_ssh import ROOT

RESULTS = ROOT / "test-results/nas-parity"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main():
    comparisons = {}
    folder = RESULTS / "aligned/antares"
    if (folder / "leroy-run.json").exists():
        pair, run = read(folder / "pair.json"), read(folder / "leroy-run.json")
        jenkins = (folder / "jenkins-console.log").read_text()
        leroy = (folder / "leroy-dependencies.log").read_text()
        advisories = [sorted(set(re.findall(r"GHSA-[a-z0-9-]+", log))) for log in (jenkins, leroy)]
        assert advisories[0] and advisories[0] == advisories[1]
        assert all("6 high severity vulnerabilities" in log for log in (jenkins, leroy))
        assert pair["jenkins"]["result"] == "FAILURE" and not pair["jenkins"]["building"]
        assert run["status"] == "failed" and run["commit"] == pair["commit"]
        steps = {s["id"]: s for s in run["steps"]}
        assert steps["dependencies"]["exit_code"] == 1
        assert all(steps[s]["status"] == "skipped" for s in ("static", "tests", "build", "browsers"))
        comparison = {
            "pipeline": "antares-ci",
            "commit": run["commit"],
            "jenkins_build": pair["jenkins"]["number"],
            "leroy_run": run["id"],
            "image": run["image_digest"],
            "round": "aligned",
            "failing_gate": "npm audit --omit=dev --audit-level=high",
            "gate_exit_code": 1,
            "high_vulnerabilities": 6,
            "same_advisories": True,
            "advisories": advisories[0],
            "compared_stages": ["checkout", "toolchain", "postgres", "dependencies", "cleanup"],
            "uncompared_stages": ["static", "tests", "build", "browsers"],
            "complete_pipeline_parity": False,
            "workload_success": False,
            "application_patches_applied": False,
        }
        write(folder / "comparison.json", comparison)
        comparisons["antares-ci"] = comparison
    folder = RESULTS / "aligned/home-lab-ci"
    if (folder / "leroy-run.json").exists():
        pair, run = read(folder / "pair.json"), read(folder / "leroy-run.json")
        jenkins = (folder / "jenkins-console.log").read_text()
        assert pair["jenkins"]["result"] == "SUCCESS" and not pair["jenkins"]["building"]
        assert run["status"] == "succeeded" and run["commit"] == pair["commit"]
        base = run["outputs"]["diff_base"]
        assert "Diff base: " + base + "; changed files: 0" in jenkins
        assert not run["outputs"]["build_required"]
        comparison = {
            "pipeline": "home-lab-ci",
            "commit": run["commit"],
            "jenkins_build": pair["jenkins"]["number"],
            "leroy_run": run["id"],
            "image": run["image_digest"],
            "round": "aligned",
            "diff_base": base,
            "changed_files": [],
            "build_publish_skipped_both": True,
            "observed_scenario_parity": True,
            "workload_success": True,
            "complete_pipeline_parity": False,
            "uncompared_paths": ["actual_image_build_and_push"],
            "application_patches_applied": False,
        }
        write(folder / "comparison.json", comparison)
        comparisons["home-lab-ci"] = comparison
    folder = RESULTS / "aligned/nikicas-hub-ci"
    if (folder / "artifact-comparison.json").exists():
        pair, run = read(folder / "pair.json"), read(folder / "leroy-run.json")
        artifacts = read(folder / "artifact-comparison.json")
        assert pair["jenkins"]["result"] == "SUCCESS" and not pair["jenkins"]["building"]
        assert run["status"] == "succeeded" and run["commit"] == pair["commit"]
        assert artifacts["same_runtime_configuration"]
        assert artifacts["same_application_contents_and_permissions"]
        comparison = {
            "pipeline": "nikicas-hub-ci",
            "commit": run["commit"],
            "jenkins_build": pair["jenkins"]["number"],
            "leroy_run": run["id"],
            "round": "aligned",
            "workload_success": True,
            "observed_scenario_parity": True,
            "complete_pipeline_parity": True,
            "application_patches_applied": False,
            "artifacts": artifacts,
            "scope": "image build and push into isolated registry; deployment compared separately",
        }
        write(folder / "comparison.json", comparison)
        comparisons["nikicas-hub-ci"] = comparison
    for name in (
        "gitea-bootstrap-repo",
        "music-library-sync-smartphone",
        "paperless-ngx-bootstrap-rules",
        "graphato-bootstrap-host",
    ):
        folder = RESULTS / "aligned" / name
        if not (folder / "leroy-target-state.json").exists():
            continue
        pair, run = read(folder / "pair.json"), read(folder / "leroy-run.json")
        assert pair["jenkins"]["result"] == "SUCCESS" and not pair["jenkins"]["building"]
        assert run["status"] == "succeeded"
        assert read(folder / "jenkins-target-state.json") == read(folder / "leroy-target-state.json")
        comparison = {
            "pipeline": name,
            "commit": pair["commit"],
            "supporting_repository_commit": run.get("commit"),
            "jenkins_build": pair["jenkins"]["number"],
            "leroy_run": run["id"],
            "round": "aligned",
            "workload_success": True,
            "observed_scenario_parity": True,
            "complete_pipeline_parity": True,
            "application_patches_applied": False,
            "parameters": pair["parameters"],
            "target_states_equal": True,
            "setup_attempts": pair.get("setup_attempts", []),
            "scope": "prepared scenario on separate fresh test destinations",
        }
        write(folder / "comparison.json", comparison)
        comparisons[name] = comparison
    hub_deploy = RESULTS / "aligned/nikicas-hub-deploy"
    if (hub_deploy / "leroy-target-state.json").exists():
        targets = [read(hub_deploy / (engine + "-target-state.json")) for engine in ("jenkins", "leroy")]
        apps = [next(c for c in state["containers"] if c["service"] == "app") for state in targets]
        assert apps[0]["image"] == apps[1]["image"]
        assert targets[0]["compose_sha256"] == targets[1]["compose_sha256"]
        assert (
            apps[0]["database_open_failure_observed"] and not apps[0]["runtime_permissions"]["data_writable"]
        )
        assert apps[1]["health"] == "healthy" and apps[1]["http_probe_exit_code"] == 0
        assert apps[1]["runtime_permissions"]["data_writable"] and apps[1]["restart_count"] == 0
        for name in ("nikicas-hub-bootstrap-host", "nikicas-hub-deploy"):
            folder = RESULTS / "aligned" / name
            pair, run = read(folder / "pair.json"), read(folder / "leroy-run.json")
            assert pair["jenkins"]["result"] == "SUCCESS" and not pair["jenkins"]["building"]
            assert run["status"] == "succeeded"
            comparison = {
                "pipeline": name,
                "commit": pair["commit"],
                "supporting_repository_commit": run.get("commit"),
                "jenkins_build": pair["jenkins"]["number"],
                "leroy_run": run["id"],
                "round": "aligned",
                "comparison_completed": True,
                "complete_pipeline_parity": False,
                "application_patches_applied": False,
                "observed_behavior_difference": "Leroy aligns bind mount permissions with runtime UID and waits for application health",
                "leroy_runtime_correction_validated": True,
                "same_deployed_image": apps[0]["image"],
                "same_compose_source": targets[0]["compose_sha256"],
                "jenkins_job_success_but_application_unhealthy": True,
                "leroy_application_healthy": True,
                "scope": "fresh test VM where deploy UID is 1001 and image UID is 1000; public ACME blocked",
            }
            write(folder / "comparison.json", comparison)
            comparisons[name] = comparison
    for name in (
        "graphato-ci",
        "graphato-postdeploy-web",
        "graphato-postdeploy-quality",
        "graphato-release-acceptance",
    ):
        folder = RESULTS / "aligned" / name
        if (folder / "comparison.json").exists():
            comparison = read(folder / "comparison.json")
            run = read(folder / "leroy-run.json")
            assert comparison["leroy_run"] == run["id"] and comparison["commit"] == run["commit"]
            assert run["status"] in ("succeeded", "failed") and comparison["comparison_completed"]
            comparisons[name] = comparison
    baseline = read(RESULTS / "baseline.json")
    for job in baseline["pipelines"]:
        if comparison := comparisons.get(job["pipeline"]):
            job["jenkins_run"] = {
                "instance": "jenkins-parity",
                "round": "aligned",
                "build": comparison["jenkins_build"],
            }
            job["leroy_run"] = comparison["leroy_run"]
            job["comparison"] = (
                "matching_audit_failure_remaining_stages_not_compared"
                if job["pipeline"] == "antares-ci"
                else "matching_no_change_path_build_uncompared"
                if job["pipeline"] == "home-lab-ci"
                else "matching_image_build_and_application_artifacts"
                if job["pipeline"] == "nikicas-hub-ci"
                else "matching_build_delivery_and_publication"
                if job["pipeline"] == "graphato-ci"
                else "same_postdeploy_rejection_with_additional_leroy_ssh_rate_limit"
                if comparison.get("additional_leroy_transport_failure")
                else "matching_startup_failure_checks_not_executed"
                if "same_startup_failure" in comparison
                else "matching_operations_and_target_state"
                if "observed_behavior_difference" not in comparison
                else "validated_runtime_permissions_and_health_gate_difference"
            )
    all_compared = len(comparisons) == len(baseline["pipelines"])
    baseline["status"] = (
        "comparison_completed_with_failures_and_gaps" if all_compared else "partially_executed"
    )
    baseline["evaluated_pipeline_count"] = len(comparisons)
    write(RESULTS / "baseline.json", baseline)
    acceptance_path = ROOT / "docs/acceptance.json"
    acceptance = read(acceptance_path)
    parity = acceptance["original_revision_nas_parity"]
    parity["status"] = (
        "aligned_comparison_completed_with_failures_and_gaps"
        if all_compared
        else "partial_aligned_comparison"
    )
    parity["comparison_completed"] = all_compared
    parity["complete"] = False
    parity["production_replacement_ready"] = False
    parity["evaluated_pipeline_count"] = len(comparisons)
    parity["checked_at"] = datetime.now(timezone.utc).isoformat()
    parity["comparisons"] = comparisons
    parity.pop("antares", None)
    parity["jenkins_alignment"] = "test-results/nas-parity/jenkins-aligned-versions.json"
    parity["ui_regression_reports"] = [
        str(path.relative_to(ROOT)).replace("\\", "/")
        for path in (
            RESULTS / "visual/report.json",
            RESULTS / "visual-operations/report.json",
            RESULTS / "visual-route-loading/report.json",
            RESULTS / "visual-detail-loading/report.json",
            RESULTS / "visual-populated-details/report.json",
            RESULTS / "visual-graphato-live/report.json",
            RESULTS / "visual-retry/report.json",
            RESULTS / "visual-transport-retry/report.json",
            RESULTS / "visual-graphato-final/report.json",
            RESULTS / "visual-diagnostics/report.json",
        )
        if path.exists()
    ]
    write(acceptance_path, acceptance)
    print("Recorded aligned evidence:", ", ".join(comparisons))


if __name__ == "__main__":
    main()

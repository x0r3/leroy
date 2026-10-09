"""Keep source equivalence, application changes and accepted exclusions distinct."""

import hashlib
import json
import subprocess
from datetime import datetime, timezone

from nas_ssh import ROOT

ANTARES = {
    "88382cc055a8": "dependency-security-update",
    "f6f891ce7c0e": "grid-performance-and-unit-test-budgets",
    "8f8b50e3b581": "unit-test-budgets",
    "b0210d2e62da": "server-behavior-and-test-clock-and-budgets",
    "096f6e8c990e": "unit-and-integration-test-budgets",
    "23ec36f8fc84": "docker-build-performance",
    "8fdbbeeeb625": "software-graphics-behavior",
    "4837546dc6e0": "software-graphics-appearance",
    "e4e47930fc69": "server-reader-lease-correction",
    "48f0c7c6845f": "arena-timing-and-layout-behavior",
    "a81afb166c8f": "browser-test-operation-synchronization",
    "9f05b7f1aa56": "browser-test-bodyless-http-response",
    "8607cfd438c7": "application-accessibility",
    "6f28a5d84311": "browser-test-capture-clock",
    "58da3ef5d112": "application-dialog-lifecycle",
}
GRAPHATO = {
    "d053af94bdde": "fresh-host-private-control-directory",
    "78e92e09fa5f": "browser-test-ast-contract",
    "9968c226f943": "browser-test-typed-rate-limiting",
}


def git(repository, *args):
    return subprocess.check_output(["git", "-C", str(repository), *args])


def main():
    folder = ROOT / "test-results/nas-parity/followup/production-source-review"
    inventory_path = max(folder.glob("inventory-*.json"))
    inventory = json.loads(inventory_path.read_text())
    baseline = json.loads((ROOT / "test-results/nas-parity/baseline.json").read_text())
    old = json.loads((ROOT / "docs/acceptance.json").read_text())["original_revision_nas_parity"]["comparisons"]
    heads = json.loads((folder / "branch-heads.json").read_text())
    applications = {}
    configurations = [
        ("antares", ".sources/antares-capture-validation", ".sources/production-review/antares-ab245279a2c5",
         "ab245279a2c5ba85dedef1180e7fd63b7f5b1398", "58da3ef5d112f58bc0a3d1cbd75179eb71d421c1", ANTARES),
        ("graphato", ".sources/graphato-nas-validation", ".sources/production-review/graphato-ed21c2e6346a",
         "48b741264f3b8353400649f6b05abf6a9c129233", "9968c226f943eb177f31c36fa0e97e7fc7f260d5", GRAPHATO),
    ]
    for name, source, target, base, candidate, categories in configurations:
        source, target = ROOT / source, ROOT / target
        current = git(target, "rev-parse", "HEAD").decode().strip()
        assert not git(target, "status", "--porcelain").strip()
        patch = git(source, "diff", "--binary", base, candidate)
        forward = subprocess.run(["git", "-C", str(target), "apply", "--check", "-"],
                                 input=patch, capture_output=True).returncode == 0
        changes = []
        for commit in git(source, "rev-list", "--reverse", base + ".." + candidate).decode().splitlines():
            changes.append({"commit": commit, "category": categories[commit[:12]],
                            "subject": git(source, "show", "-s", "--format=%s", commit).decode().strip(),
                            "files": git(source, "diff-tree", "--no-commit-id", "--name-only", "-r", commit).decode().splitlines(),
                            "leroy_migration_prerequisite": False})
        scripts = [job["script_path"] for job in baseline["pipelines"] if job["repository"] == name]
        assert all(git(source, "show", base + ":" + path) == git(target, "show", current + ":" + path) for path in scripts)
        assert all(git(source, "show", base + ":" + path) == git(source, "show", candidate + ":" + path) for path in scripts)
        applications[name] = {"production_commit": current, "candidate_commit": candidate,
            "candidate_base": base, "patch_sha256": hashlib.sha256(patch).hexdigest(),
            "aggregate_patch_applies_cleanly": forward, "production_modified": False,
            "patches_applied_to_review_checkout": False, "jenkinsfiles_unchanged": True,
            "same_candidate_passed_both_engines": True, "changes": changes,
            "all_original_application_test_timeouts_unchanged": name != "antares",
            "all_original_application_test_assertion_source_unchanged": False,
            "same_frozen_candidate_used_by_both_engines": True,
            "successful_candidate_proves_current_production_commit": False}
    jobs = []
    for job in baseline["pipelines"]:
        name, repository = job["pipeline"], job["repository"]
        live = inventory["jobs"][name]
        commit = heads[repository]["commit"] if repository in heads else job["commit"]
        if live["inline_script_sha256"]:
            assert live["inline_script_sha256"] == job["script_sha256"]
        previous = old[name]
        excluded = name == "antares-ci"
        # The bootstrap script is in home-lab, but it installs a selected Graphato
        # revision. Its old GRAPHATO_REF cannot stand in for the current source.
        same_revision = repository != "graphato" and name != "graphato-bootstrap-host"
        jobs.append({"pipeline": name, "production_commit": commit,
                     "supporting_application_commit": heads["graphato"]["commit"] if name == "graphato-bootstrap-host" else None,
                     "configuration_sha256": live["configuration_sha256"],
                     "inline_script_unchanged": bool(live["inline_script_sha256"]),
                     "included_in_nas_acceptance": not excluded,
                     "scope": "excluded_by_user" if excluded else "current_production_source",
                     "historical_comparison_evidence": previous,
                     "same_source_historical_comparison": same_revision,
                     "complete_pipeline_parity": False if excluded or not same_revision else previous.get("complete_pipeline_parity", False),
                     "new_same_source_comparison_required": not excluded and not same_revision})
    report = {"at": datetime.now(timezone.utc).isoformat(), "read_only": True,
              "inventory_evidence": inventory_path.relative_to(ROOT).as_posix(), "applications": applications,
              "deployment_topology": "Controller and CI workers on NAS; isolated remote application targets reproduce existing Jenkins SSH deployments",
              "accepted_exclusions": [{"pipeline": "antares-ci", "reason": "User excludes Antares artifact when the NAS cannot build it; no external permanent worker"}],
              "included_pipeline_count": 12, "pipelines": jobs, "production_cutover": False,
              "production_replacement_ready": False, "scope": "Source and patch review; not a new successful CI comparison"}
    (folder / "review.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"source_review_completed": True, "included_pipeline_count": 12,
                      "patches_applied": False, "production_modified": False}))


if __name__ == "__main__":
    main()

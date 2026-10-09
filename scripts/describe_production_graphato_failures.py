"""Describe archived failures and the bounded CLI reproduction without claiming a full acceptance."""

import hashlib
import json
import tarfile
from datetime import datetime, timezone

from nas_ssh import ROOT
from stage_nas_production_graphato import COMMIT


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    folder = ROOT / "test-results/nas-parity/followup/production-source-review/failed-groups"
    collection = read(folder / "collection.json")
    assert collection["commit"] == COMMIT and collection["read_only"]
    for suite in ("web", "quality"):
        for item in collection["suites"][suite]["files"]:
            path = folder / suite / item["name"]
            assert path.stat().st_size == item["size"]
            assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
        receipt = read(folder / suite / "result.json")
        assert receipt["commit"] == COMMIT and not receipt["passed"] and receipt["cleanupComplete"]
    with tarfile.open(folder / "web/artifacts.tar.gz") as bundle:
        merge = json.load(bundle.extractfile("browser-merge/open/results.json"))
    result, = merge
    assert not result["passed"] and result["id"] == "merge"
    assert "+ 'local' - 'pendingPush'" in result["error"]
    with tarfile.open(folder / "quality/artifacts.tar.gz") as bundle:
        log = bundle.extractfile("frontend-and-deployment.log").read().decode()
    failure = "Preview admission requires its dedicated, pre-created runtime mount"
    assert "ERROR: test_current_production_compose_passes_release_policy" in log
    assert "ValueError: " + failure in log and "Ran 146 tests" in log and "FAILED (errors=1)" in log
    current, pinned = read(folder / "original-compose-policy-probe.json"), read(folder / "pinned-compose-policy-probe.json")
    assert current["commit"] == pinned["commit"] == COMMIT
    assert current["successful"] and current["tests_run"] == 1 and current["skipped"] == 0
    assert current["rendered_policy_projection"]["preview_mount"]["bind"] == {"create_host_path": False}
    assert pinned["policy_error"] == failure and pinned["rendered_policy_projection"]["preview_mount"]["bind"] == {}
    assert pinned["container_removed"] and pinned["no_docker_socket"] and pinned["network_disabled"]
    record = {"at": datetime.now(timezone.utc).isoformat(), "commit": COMMIT,
              "production_jobs": {"web": 11, "quality": 11},
              "web": {"group": "browser-merge", "failure_signature": result["error"],
                      "underlying_application_cause_classified": False},
              "quality": {"group": "frontend-and-deployment", "test": "ReleaseBoundary.test_current_production_compose_passes_release_policy",
                          "failure_signature": failure, "original_python_tests_run": 146, "errors": 1,
                          "cause_reproduced": True, "cause": "The original pinned Compose v2.40.3 omits the false create_host_path field; the original validator requires an explicit False. Compose v5.5.1 preserves it.",
                          "original_cli_image": pinned["image"], "original_cli_version": pinned["compose_version"],
                          "target_cli_version": current["compose_version"]},
              "application_patches_applied": False, "production_modified": False,
              "full_pipeline_acceptance": False, "migration_prerequisite_patch_proven": False,
              "evidence": {"collection": (folder / "collection.json").relative_to(ROOT).as_posix(),
                           "pinned_cli": (folder / "pinned-compose-policy-probe.json").relative_to(ROOT).as_posix(),
                           "target_cli": (folder / "original-compose-policy-probe.json").relative_to(ROOT).as_posix()}}
    (folder / "failure-signatures.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({"commit": COMMIT, "quality_cause_reproduced": True,
                      "web_failure_signature_recorded": True, "application_patches_applied": False,
                      "full_pipeline_acceptance": False}))


if __name__ == "__main__":
    main()

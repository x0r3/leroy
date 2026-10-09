"""Finish either UI captures or final operations for the retained master comparison."""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from contextlib import closing
from datetime import datetime, timezone

from compare_nas_antares import client
from nas_candidate_paths import candidate_checkout
from nas_operations_scope import require_operations_inputs
from nas_ssh import ROOT


def read(path):
    return json.loads(path.read_text())


def phase(script, *arguments, node=False):
    print("Frozen master final acceptance:", script, *arguments, flush=True)
    executable = ["node"] if node else [sys.executable, "-X", "utf8"]
    subprocess.run([*executable, str(ROOT / "scripts" / script), *arguments], cwd=ROOT, check=True)


def confirm_frozen_source(folder, commit):
    frozen = read(folder / "frozen-master.json")
    checkout = candidate_checkout(commit)
    assert checkout.resolve() == (ROOT / frozen["checkout"]).resolve()

    def git(*arguments):
        return subprocess.check_output(["git", "-C", str(checkout), *arguments]).decode().strip()

    assert git("rev-parse", "HEAD") == commit
    assert git("rev-parse", "HEAD^{tree}") == frozen["tree"]
    assert not git("status", "--porcelain", "--untracked-files=all")
    hashes = {}
    for name, digest in frozen["jenkinsfiles_sha256"].items():
        blob = subprocess.check_output(["git", "-C", str(checkout), "show", "HEAD:" + name])
        working = (checkout / name).read_bytes()
        assert hashlib.sha256(blob).hexdigest() == digest
        assert working == blob or working.replace(b"\r\n", b"\n") == blob
        hashes[name] = {"git_blob_sha256": digest,
                        "working_file_sha256": hashlib.sha256(working).hexdigest(),
                        "working_crlf_conversion": working != blob}
    record = {"at": datetime.now(timezone.utc).isoformat(), "commit": commit,
              "tree": frozen["tree"], "clean_checkout": True, "jenkinsfile_hashes_match": True,
              "hash_scope": "Exact Git blobs as recorded at freeze; only clean Windows CRLF conversion is accepted",
              "jenkinsfiles": hashes,
              "read_only": True, "source_changed": False}
    destination = folder / "frozen-integrity-final.json"
    assert not destination.exists(), "Preserve the first final source observation"
    destination.write_text(json.dumps(record, indent=2) + "\n")
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--phase", choices=["captures", "operations"], required=True)
    parser.add_argument("--infrastructure-only", action="store_true",
                        help="Verify the owned CI stack independently; retain any failed application acceptance")
    parser.add_argument("--operations-attempt", help="Retain a separate restart/backup attempt after diagnosing an earlier failure")
    args = parser.parse_args()
    commit = args.commit
    assert re.fullmatch(r"[a-f0-9]{40}", commit)
    assert not args.operations_attempt or re.fullmatch(r"[a-z0-9-]{1,64}", args.operations_attempt)
    folder = ROOT / "test-results/nas-parity/followup/candidates/graphato" / commit
    if args.phase == "captures":
        assert not args.infrastructure_only, "Infrastructure scope applies only to operations"
        assert not args.operations_attempt
        deadline = time.monotonic() + 9 * 3600
        while not (folder / "master-acceptance-complete.json").is_file() and time.monotonic() < deadline:
            time.sleep(10)
        assert (folder / "master-acceptance-complete.json").is_file(), "No capture of an unconfirmed execution result"
        for scenario, pipeline, options, suffix in [
            (folder, "graphato-ci", ["--allow-failed"], ""),
            (folder / "scenarios/root-private-existing-host", "graphato-release-acceptance",
             ["--allow-failed", "--release-only"], "-existing-host"),
        ]:
            output = ROOT / "test-results/nas-parity" / ("visual-graphato-" + commit[:12] + suffix)
            assert not (output / "report.json").exists(), "Inspect previous captures before repeating them"
            run_id = read(scenario / pipeline / "pair.json")["leroy_run"]
            phase("verify_nas_graphato_candidate_ui.cjs", run_id, commit, *options, node=True)
        print("Both frozen-master UI capture sets are ready for manual visual inspection.", flush=True)
        return
    reports = [ROOT / "test-results/nas-parity" / ("visual-graphato-" + commit[:12] + suffix) / "report.json"
               for suffix in ["", "-existing-host"]]
    assert all(read(path)["passed"] and read(path)["manual_visual_review"] for path in reports)
    scope = require_operations_inputs(folder, commit, infrastructure_only=args.infrastructure_only)
    destination = folder / "final-operations-acceptance.json"
    assert not destination.exists()
    if not (folder / "release-image-pins.json").exists():
        options = ["--infrastructure-only"] if args.infrastructure_only else []
        phase("pin_nas_release_images.py", "--commit", commit, *options)
    if not (folder / "release-image-restore.json").exists():
        phase("verify_nas_release_image_restore.py", "--commit", commit)
    image_restore = read(folder / "release-image-restore.json")
    assert image_restore["passed"] and image_restore["image_ids_and_layers_match"]
    assert image_restore["temporary_restore_resources_removed"] and not image_restore["workloads_started"]
    if not (folder / "scm-baseline-nas-preview.json").exists():
        phase("verify_nas_scm_baseline.py", "--commit", commit)
    attempt = args.operations_attempt or "master-" + commit[:12]
    restart = ROOT / "test-results/nas-parity/followup/nas-stack-restart/attempts" / attempt / "report.json"
    if not restart.exists():
        prior = restart.parents[2] / "report.json"
        preserved = prior.with_name("report-before-" + attempt + ".json")
        assert prior.is_file() and not preserved.exists()
        preserved.write_bytes(prior.read_bytes())
        phase("test_nas_stack_restart.py", "--attempt", attempt)
    assert read(restart)["passed"]
    if not (folder / "release-image-smoke.json").exists():
        phase("verify_nas_pinned_job_images.py", "--commit", commit, "--restart-attempt", attempt)
    smoke = read(folder / "release-image-smoke.json")
    assert smoke["passed"] and smoke["all_profile_image_ids_match"] and smoke["artifact_hashes_match"]
    assert smoke["previous_diagnostic_definition_restored"]
    backup = ROOT / "test-results/nas-parity/followup/nas-backup/attempts" / attempt / "report.json"
    if not backup.exists():
        phase("test_nas_backup.py", "--attempt", attempt)
    assert read(backup)["passed"] and read(backup)["restored_controller_ready"]
    if not (folder / "nas-release-configuration-final.json").exists():
        phase("capture_nas_release_configuration.py", "--commit", commit, "--phase", "final")
    before, after = [read(folder / ("nas-release-configuration-" + name + ".json")) for name in ["before", "final"]]
    assert {name: row["image_id"] for name, row in before["services"].items()} == {
        name: row["image_id"] for name, row in after["services"].items()}
    assert {name: row["image_id"] for name, row in before["job_profiles"].items()} == {
        name: row["image_id"] for name, row in after["job_profiles"].items()}
    for name, original in before["services"].items():
        assert all(original[field] == after["services"][name][field] for field in [
            "container_id", "memory_bytes", "memory_and_swap_bytes", "memory_reservation_bytes", "nano_cpus"])
    for name, original in before["job_profiles"].items():
        assert all(original[field] == after["job_profiles"][name][field] for field in [
            "memory", "memory_swap", "cpus", "rootfs_layers"])
    pins = read(folder / "release-image-pins.json")
    assert after["configuration_sha256"]["config/runner.toml"] == pins["runner_configuration_sha256"]
    for name in ["compose.yaml", "dind.sh", "config/leroy.toml"]:
        assert before["configuration_sha256"][name] == after["configuration_sha256"][name]
    assert "compose.release.json" in after["configuration_sha256"]
    assert read(folder / "local-release-code-before.json") == read(folder / "local-release-code-final.json")
    with closing(client()) as api:
        assert api.get("/health/ready").status_code == 200
        assert not any(p["enabled"] for p in api.get("/api/pipelines").json())
        assert not any(api.get("/api/runs", params={"status": status}).json() for status in ["queued", "running", "waiting"])
    integrity = confirm_frozen_source(folder, commit)
    record = {"at": datetime.now(timezone.utc).isoformat(), "commit": commit, "passed": True,
              "acceptance_scope": scope,
              "image_layers_unchanged": True, "image_references_pinned": True,
              "tested_resources_unchanged": True, "local_core_code_unchanged": True,
              "frozen_source_integrity": integrity.relative_to(ROOT).as_posix(),
              "release_image_restore": (folder / "release-image-restore.json").relative_to(ROOT).as_posix(),
              "full_stack_restart": restart.relative_to(ROOT).as_posix(),
              "pinned_profile_smoke_jobs": (folder / "release-image-smoke.json").relative_to(ROOT).as_posix(),
              "backup_restore": backup.relative_to(ROOT).as_posix(),
              "scm_baseline_preview": (folder / "scm-baseline-nas-preview.json").relative_to(ROOT).as_posix(),
              "manual_visual_reviews": [path.relative_to(ROOT).as_posix() for path in reports],
              "all_test_triggers_disabled": True, "production_modified": False, "production_cutover": False,
              "production_credentials_migrated": False,
              "scope": "Owned CI infrastructure verification; application workload outcomes remain in acceptance_scope and are not changed by these checks"}
    destination.write_text(json.dumps(record, indent=2) + "\n")
    completion_path = folder / "master-acceptance-complete.json"
    completion = read(completion_path)
    assert completion["commit"] == commit and not completion["application_patches_applied"]
    completion.update(manual_visual_review_pending=False, final_operations_acceptance_pending=False,
                      application_workload_success_both=scope["application_workload_success_both"],
                      production_replacement_ready=False,
                      final_operations_evidence=destination.relative_to(ROOT).as_posix(),
                      final_operations_completed_at=record["at"])
    completion_path.write_text(json.dumps(completion, indent=2) + "\n")
    print(json.dumps(record), flush=True)


if __name__ == "__main__":
    main()

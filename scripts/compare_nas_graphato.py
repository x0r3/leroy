"""Compare completed, unchanged-source Graphato deliveries and their observed acceptance outcomes."""

import argparse
import ast
import hashlib
import json
import re
import subprocess
import tarfile
from collections import Counter
from pathlib import PurePosixPath

from nas_candidate_paths import comparison_source
from nas_ssh import ROOT

RESULTS = ROOT / "test-results/nas-parity/aligned"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def application_patches(candidate):
    if not candidate:
        return False
    source, _ = comparison_source("graphato-ci", candidate)
    return source["application_patches_applied"]


def environment_scope(pair):
    differences = []
    if pair.get("network_policy_evidence"):
        policies = {}
        for engine in ("jenkins", "leroy"):
            path = (ROOT / pair["network_policy_evidence"][engine]).resolve()
            assert path.is_relative_to((ROOT / "test-results/nas-parity/followup/vm-network").resolve())
            record = read(path)
            assert record["passed"] and record["application_commit"] is None
            assert record["route_before"] == record["route_after"] and len(record["networks"]) == 4
            policies[engine] = record["pool"]
        assert policies["jenkins"] == policies["leroy"] == [{"base": "10.211.0.0/16", "size": 24}]
        return {
            "identical_environment_asserted": False,
            "declared_environment_differences": [],
            "docker_network_policy_matched": True,
            "network_policy_evidence": pair["network_policy_evidence"],
        }
    if pair.get("vm_restore_attempt") == "network-pool-fix":
        folder = ROOT / "test-results/nas-parity/followup/vm-network"
        evidence = []
        for pattern, candidate in ((pair["commit"][:12] + "-*.json", pair["commit"]), ("fresh-*.json", None)):
            matches = [(path, read(path)) for path in folder.glob(pattern)]
            matches = [(path, record) for path, record in matches if record["config_changed"]]
            (path, record), = matches
            assert record["passed"] and record["application_commit"] == candidate
            assert record["pool"] == [{"base": "10.211.0.0/16", "size": 24}]
            assert record["route_before"] == record["route_after"] and len(record["networks"]) == 4
            if candidate:
                assert record["held_seconds"] == 70
            evidence.append(path.relative_to(ROOT).as_posix())
        differences.append({
            "component": "isolated target VM Docker address allocation",
            "jenkins": "Docker default address pools",
            "leroy": [{"base": "10.211.0.0/16", "size": 24}],
            "reason": "Avoid a reproduced collision with the SSH client's return route",
            "jenkins_rerun_with_corrected_pool": False,
            "evidence": evidence,
        })
    return {"identical_environment_asserted": False, "declared_environment_differences": differences}


def archived_rust_tests(directory, receipt):
    """Read bounded regular entries in memory; never unpack remote paths."""
    (bundle,) = directory.rglob("artifacts.tar.gz")
    with tarfile.open(bundle, "r:gz") as archive:
        names, total = set(), 0
        for member in archive:
            path = PurePosixPath(member.name)
            assert member.isfile() and not path.is_absolute() and ".." not in path.parts
            assert member.name not in names and 0 <= member.size <= 64 * 1024**2
            names.add(member.name)
            total += member.size
            assert len(names) <= 1000 and total <= 256 * 1024**2
        archived = json.load(archive.extractfile("result.json"))
        assert all(archived[key] == receipt[key] for key in (
            "commit", "runtimeImageId", "sourceSha256", "buildTimestamp", "suite", "runId", "checks",
        ))
        log = archive.extractfile("server-test.log").read().decode("utf-8")
        timings = json.load(archive.extractfile("rust-test-times.json"))
        assert all(timings[key] == receipt[key] for key in (
            "commit", "runtimeImageId", "sourceSha256", "buildTimestamp", "suite",
        ))
    events = []
    for line in log.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    expected = sum(event["test_count"] for event in events if event.get("type") == "suite" and event.get("event") == "started")
    terminal = Counter(
        (event["name"], event["event"]) for event in events
        if event.get("type") == "test" and event.get("event") in {"ok", "ignored", "failed"}
    )
    counts = {state: sum(count for (_, event), count in terminal.items() if event == state) for state in ("ok", "ignored", "failed")}
    assert expected > 0 and sum(counts.values()) == expected and counts["failed"] == 0
    assert timings["complete"] and timings["expectedTests"] == timings["measuredTests"] == counts["ok"]
    for test in (
        "postdeploy_state_is_private_for_fresh_and_existing_directories",
        "postdeploy_state_rejects_symlinks_and_files_without_changing_them",
    ):
        assert any(name.endswith("::" + test) and event == "ok" for name, event in terminal), test
    normalized = sorted((name, event, count) for (name, event), count in terminal.items())
    return {
        "expected": expected, **counts,
        "test_events_sha256": hashlib.sha256(json.dumps(normalized).encode()).hexdigest(),
        "ignored_tests": sorted(name for name, event in terminal if event == "ignored"),
    }


def candidate_suites(candidate, targets, ci_run):
    for engine in ("jenkins", "leroy"):
        purpose = "graphato-" + engine + "-" + candidate[:12]
        pair = read(RESULTS / "graphato-ci/pair.json")
        attempt = pair.get("vm_restore_attempt" if engine == "leroy" else "jenkins_vm_restore_attempt")
        if attempt:
            assert re.fullmatch("[a-z][a-z0-9-]{0,39}", attempt)
            purpose += "-" + attempt
        restored = read(ROOT / "test-results/nas-parity/vm-restores" / (purpose + ".json"))
        assert restored["restored"] == "nas-parity-base" and restored["purpose"] == purpose
    staged = read(RESULTS / "staged.json")
    checkout = ROOT / (".sources/production-review/graphato-" + candidate[:12]) if staged.get("source_kind") == "observed_production_revision" else ROOT / ".sources/graphato-nas-validation"
    source = subprocess.check_output(
        [
            "git",
            "-C",
            str(checkout),
            "show",
            candidate + ":deployments/linux/host/postdeploy.py",
        ],
        text=True,
    )
    constants = {}
    for statement in ast.parse(source).body:
        if isinstance(statement, ast.Assign):
            for name in statement.targets:
                if isinstance(name, ast.Name) and name.id in {"WEB_CASES", "QUALITY_CHECKS"}:
                    constants[name.id] = ast.literal_eval(statement.value)
    required = {
        "web": {"browser-core", *("browser-" + name for name in constants["WEB_CASES"])},
        "quality": set(constants["QUALITY_CHECKS"]),
    }
    assert len(required["web"]) == 21 and len(required["quality"]) == 8
    parent = read(RESULTS / "graphato-release-acceptance/pair.json")["leroy_run"]
    comparisons = {}
    rust_tests = {}
    for pipeline in (
        "graphato-bootstrap-host",
        "graphato-release-acceptance",
        "graphato-postdeploy-web",
        "graphato-postdeploy-quality",
    ):
        folder = RESULTS / pipeline
        pair, run = read(folder / "pair.json"), read(folder / "leroy-run.json")
        assert pair["jenkins"]["result"] == "SUCCESS" and not pair["jenkins"]["building"]
        assert run["status"] == "succeeded" and run["commit"] == pair["commit"]
        assert all(step["status"] == "succeeded" for step in run["steps"])
        if pipeline != "graphato-bootstrap-host":
            assert run["commit"] == candidate
            assert run["parent_id"] == (ci_run["id"] if pipeline == "graphato-release-acceptance" else parent)
        if pipeline.startswith("graphato-postdeploy-"):
            suite = pipeline.removeprefix("graphato-postdeploy-")
            for engine, archive in (
                ("jenkins", folder / f"jenkins-{pair['jenkins']['number']}-artifacts"),
                ("leroy", folder / "leroy-artifacts"),
            ):
                receipts = [read(path) for path in archive.rglob("result.json")]
                (receipt,) = [
                    value for value in receipts if value.get("suite") == suite and "checks" in value
                ]
                target = targets[engine]["receipt"]
                assert all(
                    receipt[key] == target[key]
                    for key in ("commit", "runtimeImageId", "sourceSha256", "buildTimestamp")
                )
                assert receipt["requestedGroup"] == "all" and receipt["reused"] == []
                assert (
                    receipt["passed"]
                    and receipt["requestedPassed"]
                    and receipt["cleanupComplete"]
                    and receipt["activeRelease"]
                )
                assert not receipt["cancelled"] and receipt["completedAt"] > receipt["startedAt"]
                assert set(receipt["checks"]) == required[suite]
                assert all(
                    value["passed"] is True and value["exitCode"] == 0 for value in receipt["checks"].values()
                )
                if suite == "quality":
                    rust_tests[engine] = archived_rust_tests(archive, receipt)
        comparisons[pipeline] = {
            "jenkins_build": pair["jenkins"]["number"],
            "leroy_run": run["id"],
            "workload_success_both": True,
        }
        write(
            folder / "comparison.json",
            {"commit": pair["commit"], "application_patches_applied": application_patches(candidate), **comparisons[pipeline]},
        )
    for target in targets.values():
        assert target["receipt"]["status"] == "verified"
        assert all(
            value == {"state": "passed", "missingChecks": []}
            for value in target["receipt"]["suites"].values()
        )
    assert rust_tests["jenkins"] == rust_tests["leroy"]
    write(
        RESULTS / "comparison.json",
        {
            "commit": candidate,
            "application_patches_applied": application_patches(candidate),
            "workload_success_both": True,
            "fresh_target_per_engine": True,
            **environment_scope(read(RESULTS / "graphato-ci/pair.json")),
            "reused_checks": [],
            "required_checks": {name: sorted(checks) for name, checks in required.items()},
            "rust_tests": rust_tests,
            "pipelines": comparisons,
            "delivery": read(RESULTS / "graphato-ci/comparison.json"),
        },
    )
    print("Both complete candidate acceptance suites and their fresh-target receipts verified.")


def main():
    global RESULTS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate")
    parser.add_argument("--delivery-only", action="store_true", help="Verify CI delivery independently of terminal downstream suite failures")
    args = parser.parse_args()
    assert not args.delivery_only or args.candidate, "A delivery-only check requires an explicit frozen revision"
    if args.candidate:
        _, folder = comparison_source("graphato-ci", args.candidate)
        RESULTS = folder.parent
    folder = RESULTS / "graphato-ci"
    if args.candidate and not args.delivery_only:
        outcomes = {}
        for pipeline in (
            "graphato-bootstrap-host", "graphato-ci", "graphato-release-acceptance",
            "graphato-postdeploy-web", "graphato-postdeploy-quality",
        ):
            pair = read(RESULTS / pipeline / "pair.json")
            run = read(RESULTS / pipeline / "leroy-run.json")
            assert not pair["jenkins"]["building"]
            assert run["status"] not in {"queued", "running", "waiting"}
            outcomes[pipeline] = {
                "jenkins_build": pair["jenkins"]["number"],
                "jenkins_result": pair["jenkins"]["result"],
                "leroy_run": run["id"], "leroy_status": run["status"],
                "workload_success_both": pair["jenkins"]["result"] == "SUCCESS"
                and run["status"] == "succeeded",
            }
        if not all(row["workload_success_both"] for row in outcomes.values()):
            write(RESULTS / "comparison.json", {
                "commit": args.candidate, "application_patches_applied": application_patches(args.candidate),
                "workload_success_both": False, "pipelines": outcomes,
                **environment_scope(read(folder / "pair.json")),
                "scope": "Completed execution outcomes; failed suites prevent full acceptance",
            })
            raise SystemExit("Comparison recorded: at least one completed pipeline failed.")
    targets = {engine: read(folder / f"{engine}-final-state.json") for engine in ("jenkins", "leroy")}
    pair, run = read(folder / "pair.json"), read(folder / "leroy-run.json")
    assert pair["jenkins"]["result"] == "SUCCESS" and not pair["jenkins"]["building"]
    assert run["status"] == "succeeded" and run["commit"] == pair["commit"]
    assert all(s["status"] == "succeeded" for s in run["steps"])
    pattern = r"FROM ([^\s]+@sha256:[a-f0-9]{64})"
    bases = {
        "jenkins": sorted(
            set(
                re.findall(
                    pattern,
                    (folder / f"jenkins-{pair['jenkins']['number']}-console.log").read_text(encoding="utf-8"),
                )
            )
        ),
        "leroy": sorted(
            set(
                re.findall(
                    pattern,
                    "\n".join(
                        (folder / f"leroy-{step}.log").read_text(encoding="utf-8")
                        for step in ("server", "desktop")
                    ),
                )
            )
        ),
    }
    assert len(bases["jenkins"]) == 6 and bases["jenkins"] == bases["leroy"]
    dynamic = {"image-config.json", "worker-image-config.json", "image.tar.gz"}
    compared_files, containers, desktop_metadata = {}, {}, {}
    for engine, target in targets.items():
        manifest, receipt = target["manifest"], target["receipt"]
        assert manifest["commit"] == receipt["commit"] == pair["commit"]
        assert target["verification_source_sha256"] == receipt["sourceSha256"]
        assert receipt["runtimeImageId"] == manifest["runtimeImageId"]
        assert receipt["buildTimestamp"] == manifest["build"]["timestamp"] and receipt["activeRelease"]
        assert target["anonymous_status"] == 401
        for probe in target["health_probes"].values():
            assert (
                probe["status"] == 200 and probe["database"] == "postgresql" and probe["protocolVersion"] == 1
            )
            assert probe["build"] == manifest["build"]
        compared_files[engine] = {k: v for k, v in manifest["files"].items() if k not in dynamic}
        rows = []
        for container in target["containers"]:
            assert (
                container["running"] and container["health"] == "healthy" and container["restart_count"] == 0
            )
            expected = (
                manifest["agentTestWorker"]["runtimeImageId"]
                if container["service"] == "agent-test-worker"
                else manifest["runtimeImageId"]
            )
            if container["service"] != "postgres":
                assert container["image"] == expected
            rows.append(
                {k: v for k, v in container.items() if k != "image" or container["service"] == "postgres"}
            )
        containers[engine] = rows
        (desktop,) = target["desktop_publication"]
        assert desktop["latest_matches"] and desktop["crc_verified"]
        assert desktop["manifest"]["sourceCommit"] == pair["commit"]
        assert desktop["manifest"]["buildTimestamp"] == manifest["build"]["timestamp"]
        desktop_metadata[engine] = {
            k: desktop["manifest"][k] for k in ("schemaVersion", "component", "version", "sourceCommit")
        }
    assert compared_files["jenkins"] == compared_files["leroy"]
    assert containers["jenkins"] == containers["leroy"]
    assert desktop_metadata["jenkins"] == desktop_metadata["leroy"]
    comparison = {
        "pipeline": "graphato-ci",
        "commit": pair["commit"],
        "round": "candidate" if args.candidate else "aligned",
        "jenkins_build": pair["jenkins"]["number"],
        "leroy_run": run["id"],
        "comparison_completed": True,
        "workload_success": True,
        "observed_scenario_parity": True,
        "complete_pipeline_parity": True,
        "application_patches_applied": application_patches(args.candidate),
        **environment_scope(pair),
        "same_verification_sources_and_release_policy": True,
        "same_base_image_digests": bases["jenkins"],
        "compared_files": compared_files["jenkins"],
        "same_healthy_runtime_policy": True,
        "desktop_publications_verified": True,
        "scope": "build, original release boundaries, deployment and portable publication; downstream suites evaluated separately",
        "binary_byte_identity_asserted": False,
        "build_timestamps_differ": targets["jenkins"]["manifest"]["build"]["timestamp"]
        != targets["leroy"]["manifest"]["build"]["timestamp"],
        "timings_are_not_a_performance_comparison": True,
    }
    write(folder / "comparison.json", comparison)
    print("Graphato CI delivery and publication compared.")
    if args.delivery_only:
        return
    if args.candidate:
        candidate_suites(args.candidate, targets, run)
        return
    # Diagnose the same startup failure explicitly; never count missing tests as passed.
    failures = {e: read(folder / f"{e}-postdeploy-startup-failure.json") for e in targets}
    assert failures["jenkins"] == failures["leroy"]
    assert failures["jenkins"]["checks_started"] is False
    assert failures["jenkins"]["error"] == "Run markers require root-private directories"
    assert targets["jenkins"]["receipt"]["suites"] == targets["leroy"]["receipt"]["suites"]
    rate_limit = read(folder / "leroy-postdeploy-ssh-rate-limit.json")
    assert rate_limit["ssh_limit_blocks"] and rate_limit["policy_modified"] is False
    acceptance_id = read(RESULTS / "graphato-release-acceptance/pair.json")["leroy_run"]
    for pipeline in ("graphato-postdeploy-web", "graphato-postdeploy-quality", "graphato-release-acceptance"):
        target = RESULTS / pipeline
        child_pair, child_run = read(target / "pair.json"), read(target / "leroy-run.json")
        assert child_pair["jenkins"]["result"] == "FAILURE" and not child_pair["jenkins"]["building"]
        assert child_run["status"] == "failed" and child_run["commit"] == pair["commit"]
        assert child_run["parent_id"] == (
            run["id"] if pipeline == "graphato-release-acceptance" else acceptance_id
        )
        suites = ["web", "quality"]
        if pipeline != "graphato-release-acceptance":
            suite = pipeline.removeprefix("graphato-postdeploy-")
            suites = [suite]
            for archive in (target / "jenkins-1-artifacts", target / "leroy-artifacts"):
                cancellations = list(archive.rglob("cancellation.json"))
                assert len(cancellations) == 1
                cancellation = read(cancellations[0])
                assert cancellation["suite"] == suite and cancellation["commit"] == pair["commit"]
                assert (
                    cancellation["status"] == "unconfirmed" and cancellation["errorType"] == "JSONDecodeError"
                )
                assert not list(archive.rglob("result.json")), (
                    "A check receipt requires its own result analysis"
                )
        for receipt in (targets[e]["receipt"] for e in targets):
            assert receipt["status"] == "delivered"
            assert all(s["state"] == "missing" for s in receipt["suites"].values())
        leroy_logs = "\n".join(p.read_text(encoding="utf-8") for p in target.glob("leroy-*.log"))
        jenkins_logs = (target / "jenkins-1-console.log").read_text(encoding="utf-8")
        ssh_timeout = "Connection timed out during banner exchange" in leroy_logs or (
            pipeline == "graphato-release-acceptance"
            and "release_status" in leroy_logs
            and "returned non-zero exit status 255" in leroy_logs
        )
        assert "Connection timed out during banner exchange" not in jenkins_logs
        value = {
            "pipeline": pipeline,
            "commit": pair["commit"],
            "round": "aligned",
            "jenkins_build": child_pair["jenkins"]["number"],
            "leroy_run": child_run["id"],
            "comparison_completed": True,
            "workload_success": False,
            "observed_scenario_parity": not ssh_timeout,
            "complete_pipeline_parity": False,
            "application_patches_applied": False,
            "same_startup_failure": failures["jenkins"],
            "additional_leroy_transport_failure": ssh_timeout,
            "transport_failure_evidence": (
                "aligned/graphato-ci/leroy-postdeploy-ssh-rate-limit.json" if ssh_timeout else None
            ),
            "uncompared_checks": {
                s: targets["jenkins"]["receipt"]["suites"][s]["missingChecks"] for s in suites
            },
            "scope": (
                "same postdeploy directory rejection; additional Leroy SSH rate-limit timeout during diagnostics/status; no checks passed"
                if ssh_timeout
                else "matched rejection before test execution; no browser or quality check passed"
            ),
        }
        write(target / "comparison.json", value)
        print(pipeline, "startup failure compared; suites remain unexecuted.")


if __name__ == "__main__":
    main()

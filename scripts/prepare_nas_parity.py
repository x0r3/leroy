"""Freeze unchanged source identities for NAS comparison; never start or publish jobs."""

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git(repository, *arguments):
    return subprocess.check_output(["git", "-C", str(repository), *arguments])


def sha256(content):
    return hashlib.sha256(content).hexdigest()


def prepare(root):
    inventory = json.loads((root / "docs/jenkins-inventory.json").read_text(encoding="utf-8"))
    sources, jobs, differences = {}, [], []
    for name, commit in inventory["repositories"].items():
        repository = root / ".sources" / name
        actual = git(repository, "rev-parse", "HEAD").decode().strip()
        if actual != commit or git(repository, "status", "--porcelain").strip():
            raise ValueError(f"Original checkout {name} must be clean and at {commit}")
        sources[name] = {
            "commit": commit,
            "tree": git(repository, "rev-parse", commit + "^{tree}").decode().strip(),
            "application_patches_applied": False,
        }
    for job in inventory["jobs"]:
        name, repository = job["name"], job["source_repository"]
        if job["script_paths"]:
            path = job["script_paths"][0]
            raw = git(root / ".sources" / repository, "show", job["source_commit"] + ":" + path)
        else:
            path = ".sources/jenkins/" + name + ".Jenkinsfile"
            # Inline XML text is represented with LF, independently of Windows checkout settings.
            raw = (root / path).read_bytes().replace(b"\r\n", b"\n")
        actual = sha256(raw)
        if actual != job["script_sha256"]:
            differences.append(
                {
                    "kind": "historical_script_hash_mismatch",
                    "pipeline": name,
                    "recorded": job["script_sha256"],
                    "git_blob": actual,
                    "resolution": "Use the identified original Git blob; verify live Jenkins configuration before execution",
                }
            )
        jobs.append(
            {
                "pipeline": name,
                "repository": repository,
                "commit": job["source_commit"],
                "script_path": path,
                "script_sha256": actual,
                "captured_jenkins_status": job["color"],
                "automatic_triggers": False,
                "jenkins_run": None,
                "leroy_run": None,
                "comparison": "not_run",
            }
        )
    return {
        "schema_version": 1,
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "status": "prepared_not_executed",
        "nas_parity_passed": False,
        "sources": sources,
        "pipelines": jobs,
        "inventory_differences": differences,
        "required_comparison_inputs": [
            "actual source commit and clean tree for both runs",
            "live Jenkins definition and effective command arguments",
            "runner image IDs; Node/npm/Python/Docker/Compose versions and effective UID/GID",
            "test/target image IDs, kernel, AppArmor and CPU/memory limits",
            "test parameters, isolated target state, cold/warm caches and previous-success baseline",
            "full independent suite execution, no reused receipts or hidden retry",
            "stage exit codes, test counts, skip/failure reasons, logs and artifact hashes",
        ],
        "known_configuration_differences": [
            {
                "component": "Node",
                "jenkins_dockerfile": "24.18.0",
                "leroy_dockerfile": "24.14.1",
                "note": "Verify the running NAS container before selecting a parity image",
            },
            {
                "component": "Antares unit-test concurrency",
                "jenkins": "npm test",
                "local_leroy_profile": "npm test -- --maxWorkers=1",
                "note": "Do not use the local test_workers override for a like-for-like run",
            },
            {
                "component": "Graphato postdeploy execution host",
                "jenkins": "remote Linux target",
                "local_leroy": "isolated Ubuntu VM",
                "note": "NAS orchestrates these tests; compare both engines against equivalent isolated target states",
            },
        ],
        "classification": {
            "migration_equivalent": "Requires matched inputs and observed behavior; equal failure status alone is insufficient",
            "workload_success": "Recorded separately; matching application failures are not a successful workload",
            "application_patches": "Separate candidates, excluded from this baseline",
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "test-results/nas-parity/baseline.json")
    args = parser.parse_args()
    report = prepare(ROOT)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Prepared {len(report['pipelines'])} unchanged pipeline baselines; no jobs executed.")
    print(f"Historical script hash differences: {len(report['inventory_differences'])}")
    print(args.output)


if __name__ == "__main__":
    main()

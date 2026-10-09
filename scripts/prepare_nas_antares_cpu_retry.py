"""Archive the completed six-CPU comparison before an explicit two-CPU repeat."""

import json
from contextlib import closing

from compare_nas_antares import client
from nas_ssh import ROOT


def main():
    folder = ROOT / "test-results/nas-parity/followup/candidates/antares/9f05b7f1aa56d709f269c37700a65785385a8391"
    comparison = json.loads((folder / "comparison.json").read_text())
    assert comparison["jenkins"]["number"] == 8 and comparison["jenkins"]["result"] == "FAILURE"
    assert comparison["leroy_run"] == "bc29298b409c4954b6ee7e41cdbf5cd2"
    assert comparison["leroy_status"] == "failed" and not comparison["execution_success_both"]
    assert comparison["resource_comparison"]["jenkins_cpus"] == 6
    proof = json.loads((folder / "local-linux-unit-two-cpu.json").read_text())
    assert proof["passed"] and not proof["oom_events"]
    with closing(client()) as api:
        response = api.get("/api/runs/" + comparison["leroy_run"])
        response.raise_for_status()
        assert response.json()["status"] == "failed"
    archive = folder / "attempts/six-cpu"
    assert archive.resolve().is_relative_to(ROOT.resolve())
    archive.mkdir(parents=True, exist_ok=False)
    for path in sorted({folder / "comparison.json", *folder.glob("jenkins-*"), *folder.glob("leroy-*")}):
        destination = archive / path.name
        assert path.resolve().is_relative_to(folder.resolve()) and destination.resolve().is_relative_to(archive.resolve())
        assert not path.is_symlink() and not destination.exists()
        path.rename(destination)
    (archive / "retry.json").write_text(json.dumps({
        "reason": "Reduce automatic Vitest parallelism via the same two-CPU Docker budget in both engines",
        "candidate_unchanged": comparison["commit"], "jenkinsfile_unchanged": True,
        "test_commands_and_timeouts_unchanged": True, "previous_runs_retained": True,
        "nas_budget_applied": False,
    }, indent=2) + "\n")
    print("Actual six-CPU failures archived; no remote configuration or run changed.")


if __name__ == "__main__":
    main()

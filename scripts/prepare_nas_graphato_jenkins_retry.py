"""Preserve the successful reference before repeating it with the same VM network pool."""

import json
import shutil

from nas_candidate_paths import comparison_source
from nas_gitea_target import idle
from nas_ssh import ROOT

CANDIDATE = "78e92e09fa5f6f4f40c5e60e2b149ab66b76987c"
ATTEMPT = "aligned-network"


def main():
    idle()
    _, ci = comparison_source("graphato-ci", CANDIDATE)
    root = ci.parent.resolve()
    assert root.is_relative_to(ROOT.resolve())
    previous = json.loads((root / "comparison.json").read_text())
    assert previous["workload_success_both"] and previous["fresh_target_per_engine"]
    restore_path = ROOT / "test-results/nas-parity/vm-restores" / (
        "graphato-jenkins-" + CANDIDATE[:12] + "-" + ATTEMPT + ".json"
    )
    restore = json.loads(restore_path.read_text())
    assert restore["restored"] == "nas-parity-base"
    policies = {
        "leroy": "test-results/nas-parity/followup/vm-network/fresh-20261004T053448Z.json",
        "jenkins": "test-results/nas-parity/followup/vm-network/fresh-20261004T225141Z.json",
    }
    for path in policies.values():
        proof = json.loads((ROOT / path).read_text())
        assert proof["passed"] and proof["application_commit"] is None
        assert proof["pool"] == [{"base": "10.211.0.0/16", "size": 24}]
    archive = root / "attempts/jenkins-before-network-alignment"
    archive.mkdir(parents=True, exist_ok=False)

    def preserve(path, destination):
        assert path.resolve().is_relative_to(root) and destination.resolve().is_relative_to(archive)
        assert not path.is_symlink() and not destination.exists()
        path.rename(destination)

    for folder in sorted(root.glob("graphato-*")):
        if not folder.is_dir():
            continue
        target = archive / folder.name
        target.mkdir()
        pair_path = folder / "pair.json"
        pair = json.loads(pair_path.read_text())
        assert pair["jenkins"]["result"] == "SUCCESS" and pair["leroy_status"] == "succeeded"
        shutil.copy2(pair_path, target / "pair.json")
        for path in sorted(folder.glob("jenkins-*")):
            preserve(path, target / path.name)
        for key in list(pair):
            if key.startswith("jenkins"):
                pair.pop(key)
        pair.update(complete=False, jenkins_vm_restore_attempt=ATTEMPT, network_policy_evidence=policies)
        pair["jenkins_previous_evidence"] = (target / "pair.json").relative_to(ROOT).as_posix()
        pair_path.write_text(json.dumps(pair, indent=2) + "\n")
        if (folder / "comparison.json").exists():
            preserve(folder / "comparison.json", target / "comparison.json")
    for path in [*sorted(root.glob("jenkins-*")), root / "comparison.json"]:
        assert path.is_file()
        preserve(path, archive / path.name)
    (archive / "retry.json").write_text(json.dumps({
        "candidate": CANDIDATE, "attempt": ATTEMPT, "source_changed": False,
        "restore": restore_path.relative_to(ROOT).as_posix(), "network_policy_evidence": policies,
        "previous_comparison_passed": True, "fresh_jenkins_suites_required": True,
    }, indent=2) + "\n")
    print("Successful previous comparison retained; same-source Jenkins network alignment prepared.")


if __name__ == "__main__":
    main()

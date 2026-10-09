"""Preserve the failed transport attempt before a fresh, same-source comparison."""

import json
import shutil
from contextlib import closing

from compare_nas_antares import client
from nas_candidate_paths import comparison_source
from nas_ssh import ROOT

CANDIDATE = "78e92e09fa5f6f4f40c5e60e2b149ab66b76987c"
ATTEMPT = "network-pool-fix"


def main():
    _, ci = comparison_source("graphato-ci", CANDIDATE)
    root = ci.parent.resolve()
    assert root.is_relative_to(ROOT.resolve())
    watch = json.loads((root / "leroy-run-watch.json").read_text())
    assert watch["candidate"] == CANDIDATE and not watch["all_successful"]
    assert watch["runs"]["graphato-ci"]["id"] == "cf28fcde74054b1fa57c8d181bf5c521"
    assert watch["runs"]["graphato-postdeploy-quality"]["status"] == "failed"
    proof = json.loads((root / "leroy-route-collision-proof.json").read_text())
    assert proof["before"] == proof["after"] and "via 10.90.0.2" in proof["before"]
    assert any(
        row["route"].startswith("local 172.23.0.1")
        and any(subnet["Subnet"] == "172.23.0.0/16" for subnet in row["subnets"])
        for row in proof["networks"]
    ), "Retain the actual reproduced routing evidence"
    restore = ROOT / "test-results/nas-parity/vm-restores" / (
        "graphato-leroy-" + CANDIDATE[:12] + "-" + ATTEMPT + ".json"
    )
    restored = json.loads(restore.read_text())
    assert restored["restored"] == "nas-parity-base"
    with closing(client()) as api:
        for status in ("running", "waiting", "queued"):
            response = api.get("/api/runs", params={"status": status})
            response.raise_for_status()
            assert not response.json()
        for row in watch["runs"].values():
            response = api.get("/api/runs/" + row["id"])
            response.raise_for_status()
            assert response.json()["status"] == row["status"]
    archive = root / "attempts" / "leroy-before-network-pool-fix"
    archive.mkdir(parents=True, exist_ok=False)
    for folder in sorted(root.glob("graphato-*")):
        if not folder.is_dir():
            continue
        target = archive / folder.name
        target.mkdir()
        pair_path = folder / "pair.json"
        pair = json.loads(pair_path.read_text())
        shutil.copy2(pair_path, target / "pair.json")
        previous = {key: value for key, value in pair.items() if key.startswith("leroy")}
        for path in sorted(folder.glob("leroy-*")):
            destination = target / path.name
            assert path.resolve().is_relative_to(root) and destination.resolve().is_relative_to(archive)
            assert not path.is_symlink() and not destination.exists()
            path.rename(destination)
        for key in list(pair):
            if key.startswith("leroy"):
                pair.pop(key)
        pair.update(complete=False, vm_restore_attempt=ATTEMPT)
        pair["leroy_attempts"] = [{
            "previous": previous,
            "evidence": (target / "pair.json").relative_to(ROOT).as_posix(),
            "reason": "Test-VM Docker network 172.23.0.0/16 shadowed the SSH source; use dedicated 10.211.0.0/16 pool",
            "source_changed": False,
            "fresh_baseline": restored["restored"],
        }]
        pair_path.write_text(json.dumps(pair, indent=2) + "\n")
    for path in sorted(root.glob("leroy-*")):
        destination = archive / path.name
        assert path.resolve().is_relative_to(root) and destination.resolve().is_relative_to(archive)
        assert path.is_file() and not path.is_symlink() and not destination.exists()
        path.rename(destination)
    (archive / "retry.json").write_text(json.dumps({
        "candidate": CANDIDATE, "restore": restore.relative_to(ROOT).as_posix(),
        "attempt": ATTEMPT, "application_source_changed": False,
        "fresh_suites_required": True, "previous_api_runs_retained": True,
    }, indent=2) + "\n")
    print("Previous Leroy evidence preserved; fresh bootstrap and complete run tree required.")


if __name__ == "__main__":
    main()

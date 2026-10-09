"""Preserve the failed paired comparison before the explicit helper-storage repeat."""

import hashlib
import json
from contextlib import closing
from datetime import datetime, timezone

from compare_nas_antares import client
from nas_gitea_target import idle
from nas_ssh import ROOT

CANDIDATE = "8607cfd438c7645012bf0482a5da83acb122d6dd"


def main():
    folder = ROOT / "test-results/nas-parity/followup/candidates/antares" / CANDIDATE
    policy = json.loads((folder / "tmpfs-policy-applied.json").read_text())
    assert policy["candidate"] == CANDIDATE and policy["jenkinsfile_and_application_sources_unchanged"]
    comparison = json.loads((folder / "comparison.json").read_text())
    assert comparison["commit"] == CANDIDATE
    assert comparison["jenkins"]["number"] == 11 and comparison["jenkins"]["result"] == "ABORTED"
    assert comparison["jenkins"]["building"] is False
    assert comparison["leroy_run"] == "b090e71eb7854c38b84414801e6c50ed"
    assert comparison["leroy_status"] == "interrupted" and not comparison["execution_success_both"]
    idle()
    with closing(client()) as api:
        response = api.get("/api/runs/" + comparison["leroy_run"])
        response.raise_for_status()
        assert response.json()["status"] == "interrupted"
    archive = folder / "attempts/without-tmpfs"
    assert archive.resolve().is_relative_to(ROOT.resolve())
    archive.mkdir(parents=True, exist_ok=False)
    rows = []
    paths = sorted({folder / "comparison.json", *folder.glob("jenkins-*"), *folder.glob("leroy-*")})
    for path in paths:
        destination = archive / path.name
        assert path.resolve().is_relative_to(folder.resolve()) and destination.resolve().is_relative_to(archive.resolve())
        assert not path.is_symlink() and not destination.exists()
        rows.append({"name": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None})
        # Both resolved absolute paths are inside this task's evidence directory.
        path.rename(destination)
    (archive / "retry.json").write_text(json.dumps({
        "at": datetime.now(timezone.utc).isoformat(), "candidate_unchanged": CANDIDATE,
        "reason": "Full original browser matrix was tested with bounded temporary storage. Apply the same verified disposable database/browser policy to both engines; retain all original assertions and time limits.",
        "jenkinsfile_unchanged": True, "previous_runs_retained": True,
        "files": rows, "runtime_policy": "../../tmpfs-policy-applied.json",
        "full_ci_acceptance": False,
    }, indent=2) + "\n")
    print("Failed Jenkins #11/Leroy #72 pair preserved in attempts/without-tmpfs; no test rerun yet.")


if __name__ == "__main__":
    main()

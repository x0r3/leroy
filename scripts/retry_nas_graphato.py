"""Explicitly retry the reconciled Graphato infrastructure failure, preserving attempt evidence."""

import argparse
import json
import shutil
from contextlib import closing
from datetime import datetime, timezone

from compare_nas_antares import client
from nas_ssh import ROOT
from prepare_nas_vm import guest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--transport", action="store_true", help="Retry the separately reconciled tunnel failure"
    )
    transport = parser.parse_args().transport
    results = ROOT / "test-results/nas-parity"
    deployment = json.loads((results / "lease-fix-deployment.json").read_text())
    assert deployment["application_patches_applied"] is False
    folder = results / "aligned/graphato-ci"
    pair = json.loads((folder / "pair.json").read_text())
    old_id = "f36b0cbe2e38402ea8d0a6cd49687e90" if transport else "efb7bc31407c463bacb6f9f2bb0d7bda"
    assert pair["leroy_run"] == old_id, "Only the explicitly reconciled attempt may be retried"
    if transport:
        proof = json.loads((results / "tunnel-recovery/transport-restored.json").read_text())
        assert proof["application_deployed"] is False
        assert (
            (folder / "leroy-deploy.log")
            .read_text()
            .startswith("ssh: connect to host graphato-vm port 12225: Connection refused")
        )
    archive = folder / "attempts" / old_id
    archive.mkdir(parents=True, exist_ok=False)
    for path in [folder / "pair.json", *folder.glob("leroy-*")]:
        if path.is_dir():
            shutil.copytree(path, archive / path.name)
        elif path.is_file():
            shutil.copy2(path, archive / path.name)
    program = """import json,pathlib,subprocess
assert pathlib.Path('/var/lib/leroy-vm/ready').is_file()
assert not pathlib.Path('/opt/graphato/current').exists()
assert not subprocess.check_output(['docker','ps','-aq','--filter','label=com.docker.compose.project=graphato-prod'],text=True).strip()
print(json.dumps({'application_deployed':False,'graphato_containers':0}))
"""
    target = json.loads(guest("sudo python3 -", program))
    with closing(client()) as api:
        response = api.get("/api/runs/" + old_id)
        response.raise_for_status()
        old = response.json()
        if transport:
            assert old["status"] == "failed" and old["reason"] == "deploy: Process exited with code 1"
            probe = api.get("/api/runs/" + proof["read_only_probe_run"])
            probe.raise_for_status()
            assert probe.json()["status"] == "succeeded"
        else:
            assert old["status"] == "interrupted" and "lease expired" in old["reason"]
        assert not old["children"]
        assert all(s["status"] == "skipped" for s in old["steps"] if s["id"] == "publish")
        assert next(s["status"] for s in old["steps"] if s["id"] == "deploy") == (
            "failed" if transport else "skipped"
        )
        assert not any(p["enabled"] for p in api.get("/api/pipelines").json())
        reason = {
            "run_id": old_id,
            "reason": old["reason"],
            "reconciled_at": datetime.now(timezone.utc).isoformat(),
            "target": target,
            "fix": "Pinned test-VM reverse tunnel restored, supervised and successfully probed"
            if transport
            else "Bounded independent heartbeats and Docker calls; 128MiB job memory reservation",
            "test_resources": "Completed comparison Jenkins and its idle builder stopped; parent limits unchanged",
            "cache": "Retry uses the existing Leroy builder cache from previous attempts",
            "performance_comparison": False,
        }
        (archive / "retry-reconciliation.json").write_text(json.dumps(reason, indent=2) + "\n")
        response = api.post("/api/runs/" + old_id + "/retry")
        response.raise_for_status()
        run = response.json()
        assert run["retry_of"] == old_id and run["commit"] == old["commit"]
        pair.setdefault("leroy_attempts", []).append(reason)
        pair["leroy_run"] = run["id"]
        pair["leroy_status"] = run["status"]
        (folder / "pair.json").write_text(json.dumps(pair, indent=2) + "\n")
        print(json.dumps({"run_id": run["id"], "retry_of": old_id, "commit": run["commit"]}))


if __name__ == "__main__":
    main()

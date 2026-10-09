"""Verify the committed Graphato repair with the same full release gates."""

import json
import re
import subprocess
import sys
import tomllib
from contextlib import closing

from test_graphato_vm import collect, full_release_passed
from test_support import ROOT, api, inner, start, wait
from test_vm import guest

assert guest("systemd-detect-virt") == "kvm"
if "--fresh-host" in sys.argv:
    assert (ROOT / ".local/vm/fresh.compose.yaml").is_file()
    guest("sudo test ! -e /opt/graphato/current")
else:
    assert guest("curl -fsS -o /dev/null -w '%{http_code}' https://graphato.test/") == "200"
names = {
    "graphato-ci",
    "graphato-release-acceptance",
    "graphato-postdeploy-web",
    "graphato-postdeploy-quality",
}
with closing(api()) as client:
    originals = {
        item["id"]: item["spec"] for item in client.get("/api/pipelines").json() if item["id"] in names
    }
    assert len(originals) == 4
    assert all(
        not spec["enabled"] and spec["repository"] in {"/sources/graphato", "/sources/graphato-validation"}
        for spec in originals.values()
    )
    commit = subprocess.check_output(
        ["git", "-C", str(ROOT / ".sources/graphato-validation"), "rev-parse", "HEAD"], text=True
    ).strip()
    try:
        for name, spec in originals.items():
            candidate = {**spec, "repository": "/sources/graphato-validation", "ref": "leroy-validation"}
            client.put("/api/pipelines/" + name, json=candidate).raise_for_status()
        run_id = start(client, "graphato-ci", commit=commit)
        print("graphato-ci", run_id, "candidate", commit, flush=True)
        wait(client, run_id, timeout=29000)
        # The dedicated test host has 16 GiB for Docker. After packaging has
        # finished, release idle BuildKit RAM before the VM's large Rust suite.
        profiles = tomllib.loads((ROOT / ".local/runner.test.toml").read_text())
        builder = profiles["profiles"]["default"]["graphato"].get("builder_name")
        if builder:
            assert re.fullmatch(r"leroy-[a-z0-9-]+", builder)
            inner("stop", "buildx_buildkit_" + builder + "0")
        result = collect(client, run_id)
        result["passed"] = full_release_passed(result)
        result["candidate_commit"] = commit
        (ROOT / "test-results/vm/graphato-validation.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8"
        )
        print(json.dumps(result), flush=True)
    finally:
        for name, spec in originals.items():
            client.put("/api/pipelines/" + name, json=spec).raise_for_status()
    raise SystemExit(0 if result["passed"] else 1)

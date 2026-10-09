"""Run the full Graphato migration on the isolated own-kernel VM, preserving all gates."""

import json
from contextlib import closing

from test_support import ROOT, api, evidence, start, wait
from test_vm import guest


def collect(client, run_id):
    run = wait(client, run_id, timeout=29000)
    evidence(client, run_id)
    children = [collect(client, child["id"]) for child in run.get("children", [])]
    return {
        "pipeline": run["pipeline_id"],
        "run": run_id,
        "status": run["status"],
        "children": children,
        "passed": run["status"] == "succeeded" and all(child["passed"] for child in children),
    }


def full_release_passed(result):
    """A deployment skipped as already current must not masquerade as acceptance."""
    expected = {
        "graphato-ci",
        "graphato-release-acceptance",
        "graphato-postdeploy-web",
        "graphato-postdeploy-quality",
    }
    pending, found = [result], []
    while pending:
        item = pending.pop()
        if not item["passed"]:
            return False
        found.append(item["pipeline"])
        pending.extend(item["children"])
    return len(found) == len(expected) and set(found) == expected


def main():
    assert guest("systemd-detect-virt") == "kvm"
    results = []
    destination = ROOT / "test-results/vm/graphato.json"
    with closing(api()) as client:
        for item in client.get("/api/pipelines").json():
            if item["spec"]["repository"] and not item["spec"]["repository"].startswith("/sources/"):
                raise ValueError("Refusing non-test repository configuration")
            if item["enabled"]:
                raise ValueError("Pause automatic triggers before acceptance")
        for pipeline, parameters in [
            (
                "graphato-bootstrap-host",
                {"DOMAIN": "graphato.test", "TARGET_HOST": "graphato-vm", "APPLY_CHANGES": False},
            ),
            (
                "graphato-bootstrap-host",
                {"DOMAIN": "graphato.test", "TARGET_HOST": "graphato-vm", "APPLY_CHANGES": True},
            ),
            ("graphato-ci", {}),
        ]:
            run_id = start(client, pipeline, parameters)
            print(pipeline, run_id, flush=True)
            result = collect(client, run_id)
            if pipeline == "graphato-ci":
                result["passed"] = full_release_passed(result)
            results.append(result)
            destination.write_text(json.dumps(results, indent=2), encoding="utf-8")
            print(pipeline, result["status"], flush=True)
            if not result["passed"]:
                raise SystemExit(1)


if __name__ == "__main__":
    main()

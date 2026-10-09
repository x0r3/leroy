"""Execute actual migrated workloads against generated local Docker targets.

Nonzero exit means acceptance is incomplete. No stage or project gate is bypassed.
Run publish_test_catalog.py and setup_test_targets.py first. This can take hours.
"""

import json
from contextlib import closing

from test_support import ROOT, api, evidence, start, wait


def main():
    cases = json.loads((ROOT / "examples/migration-cases.json").read_text(encoding="utf-8"))
    results = []
    with closing(api()) as client:
        installed = client.get("/api/pipelines").json()
        for item in installed:
            if item["spec"]["repository"] and not item["spec"]["repository"].startswith("/sources/"):
                raise ValueError("Refusing non-test repository configuration")
            if item["enabled"]:
                raise ValueError("Pause automatic triggers before migration acceptance")
        for case in cases:
            id = start(client, case["pipeline"], case.get("parameters"), case.get("commit"))
            print(case["pipeline"], id, flush=True)
            run = wait(client, id, timeout=29000)
            evidence(client, id)
            results.append({"pipeline": case["pipeline"], "run": id, "status": run["status"]})
            for child in run.get("children", []):
                wait(client, child["id"], timeout=29000)
                evidence(client, child["id"])
            (ROOT / "test-results/migration-summary.json").write_text(
                json.dumps(results, indent=2), encoding="utf-8"
            )
            print(case["pipeline"], run["status"], flush=True)
    raise SystemExit(0 if all(r["status"] == "succeeded" for r in results) else 1)


if __name__ == "__main__":
    main()

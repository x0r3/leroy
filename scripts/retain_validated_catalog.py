"""Keep proven application revisions selected in the paused, isolated test catalog."""

import json
import subprocess
from contextlib import closing

from test_support import ROOT, api

antares = json.loads((ROOT / "test-results/antares-validation.json").read_text(encoding="utf-8"))
graphato = json.loads((ROOT / "test-results/vm/graphato-validation.json").read_text(encoding="utf-8"))
assert antares["status"] == "succeeded" and graphato["passed"] is True
sources = {
    "antares": (antares["commit"], ["antares-ci"]),
    "graphato": (
        graphato["candidate_commit"],
        [
            "graphato-ci",
            "graphato-release-acceptance",
            "graphato-postdeploy-web",
            "graphato-postdeploy-quality",
        ],
    ),
}
for name, (commit, _) in sources.items():
    checkout = ROOT / ".sources" / (name + "-validation")
    actual = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
    assert actual == commit, "Validation checkout changed since acceptance"
    subprocess.run(["git", "-C", str(checkout), "diff", "--exit-code", "HEAD", "--quiet"], check=True)

with closing(api()) as client:
    for state in ("queued", "running", "waiting"):
        response = client.get("/api/runs", params={"status": state, "limit": 1})
        response.raise_for_status()
        assert not response.json(), "Drain test jobs before retaining validated revisions"
    response = client.get("/api/pipelines")
    response.raise_for_status()
    pipelines = {pipeline["id"]: pipeline for pipeline in response.json()}
    assert not any(pipeline["enabled"] for pipeline in pipelines.values())
    changes = []
    for name, (commit, names) in sources.items():
        for identifier in names:
            spec = pipelines[identifier]["spec"]
            assert spec["repository"] in {f"/sources/{name}", f"/sources/{name}-validation"}
            changes.append(
                (
                    identifier,
                    spec,
                    {
                        **spec,
                        "repository": f"/sources/{name}-validation",
                        "ref": "leroy-validation",
                    },
                    commit,
                )
            )
    applied = []
    try:
        for identifier, original, candidate, _commit in changes:
            client.put("/api/pipelines/" + identifier, json=candidate).raise_for_status()
            applied.append((identifier, original))
    except Exception:
        for identifier, original in reversed(applied):
            client.put("/api/pipelines/" + identifier, json=original).raise_for_status()
        raise
    result = [
        {"pipeline": identifier, "repository": candidate["repository"], "commit": commit}
        for identifier, _, candidate, commit in changes
    ]
    (ROOT / "test-results/catalog-validation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))

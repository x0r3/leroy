"""Use the prepared isolated targets in the NAS comparison start dialogs."""

import json
from contextlib import closing
from datetime import datetime, timezone

from compare_nas_antares import client
from nas_ssh import ROOT

from leroy.schema import Pipeline


def main():
    folder = ROOT / "test-results/nas-parity"
    with closing(client()) as api:
        response = api.get("/api/pipelines")
        response.raise_for_status()
        installed = response.json()
        assert len(installed) == 13 and not any(p["enabled"] for p in installed)
        plans = []
        for pipeline in installed:
            prepared = folder / "aligned" / pipeline["id"] / "prepared.json"
            if not prepared.exists():
                continue
            parameters = json.loads(prepared.read_text())["parameters"]
            spec = json.loads(json.dumps(pipeline["spec"]))
            changes = []
            for parameter in spec["parameters"]:
                name = parameter["name"]
                if name not in parameters:
                    continue
                value = False if name == "APPLY_CHANGES" else parameters[name]
                if parameter["kind"] == "integer":
                    value = int(value)
                if parameter["default"] != value:
                    changes.append({"name": name, "before": parameter["default"], "after": value})
                    parameter["default"] = value
            Pipeline.model_validate(spec)
            if changes:
                plans.append({"pipeline": pipeline["id"], "changes": changes, "spec": spec})
        for plan in plans:
            response = api.put("/api/pipelines/" + plan["pipeline"], json=plan["spec"])
            response.raise_for_status()
            print(plan["pipeline"], len(plan["changes"]), "test defaults aligned")
        checked = api.get("/api/pipelines")
        checked.raise_for_status()
        actual = {p["id"]: p for p in checked.json()}
        assert not any(p["enabled"] for p in actual.values())
        for plan in plans:
            assert actual[plan["pipeline"]]["spec"] == plan["spec"]
        if plans:
            marker = folder / "form-defaults.json"
            history = json.loads(marker.read_text()) if marker.exists() else []
            history.append({"at": datetime.now(timezone.utc).isoformat(), "changes": plans})
            marker.write_text(json.dumps(history, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

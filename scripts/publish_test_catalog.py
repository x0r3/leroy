"""Publish the inventoried pipelines with local test repository/profile overrides."""

import json
import tomllib
from contextlib import closing

from test_support import ROOT, api

from leroy.catalog import catalog

config = tomllib.loads((ROOT / ".local/leroy.toml").read_text(encoding="utf-8"))
for case in json.loads((ROOT / "examples/migration-cases.json").read_text(encoding="utf-8")):
    config.setdefault("pipelines", {}).setdefault(case["pipeline"], {}).setdefault("defaults", {}).update(
        case.get("parameters", {})
    )
config["pipelines"]["graphato-bootstrap-host"]["defaults"]["APPLY_CHANGES"] = False
with closing(api()) as client:
    for pipeline in catalog(config):
        pipeline.enabled = False
        if pipeline.id == "antares-ci":
            pipeline.profile = "antares"
        if pipeline.repository and not pipeline.repository.startswith("/sources/"):
            raise ValueError("Test catalog requires local source mirrors")
        response = client.put("/api/pipelines/" + pipeline.id, json=pipeline.model_dump())
        response.raise_for_status()
        print("Published", pipeline.id)

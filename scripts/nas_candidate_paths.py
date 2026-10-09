"""Keep later candidate evidence separate from every original-source comparison."""

import json
import os
import re

from nas_ssh import ROOT


def candidate_checkout(candidate):
    assert re.fullmatch("[a-f0-9]{40}", candidate)
    folder = ROOT / "test-results/nas-parity/followup/candidates/graphato" / candidate
    staged = json.loads((folder / "staged.json").read_text())
    if staged.get("source_kind") == "frozen_master_revision":
        frozen = json.loads((folder / "frozen-master.json").read_text())
        assert frozen["commit"] == candidate and not frozen["application_patches_applied"]
        checkout = (ROOT / frozen["checkout"]).resolve()
        assert checkout.is_relative_to((ROOT / ".sources/frozen-master").resolve())
        return checkout
    if staged.get("source_kind") == "observed_production_revision":
        return ROOT / (".sources/production-review/graphato-" + candidate[:12])
    return ROOT / ".sources/graphato-nas-validation"


def comparison_source(pipeline, candidate=None):
    baseline = json.loads((ROOT / "test-results/nas-parity/baseline.json").read_text())
    source = dict(next(p for p in baseline["pipelines"] if p["pipeline"] == pipeline))
    base = ROOT / "test-results/nas-parity/aligned"
    if candidate:
        assert re.fullmatch("[a-f0-9]{40}", candidate) and pipeline.startswith("graphato-")
        base = ROOT / "test-results/nas-parity/followup/candidates/graphato" / candidate
        staged = json.loads((base / "staged.json").read_text())
        assert staged["commit"] == candidate and staged["jenkinsfiles_unchanged"]
        source["application_patches_applied"] = staged["application_patches_applied"]
        if pipeline != "graphato-bootstrap-host":
            source["commit"] = candidate
        scenario = os.environ.get("LEROY_NAS_COMPARISON_SCENARIO")
        if scenario:
            assert scenario == "root-private-existing-host" and staged["source_kind"] in {
                "observed_production_revision", "frozen_master_revision"}
            assert not staged["application_patches_applied"]
            base = base / "scenarios" / scenario
            assert (base / "scenario.json").is_file(), "Explicitly prepare and record the additional scenario first"
    return source, base / pipeline

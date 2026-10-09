"""A successful old probe must never substitute for a changed NAS preflight."""

import importlib
from pathlib import Path

import pytest

from leroy.schema import Pipeline, Step


@pytest.mark.parametrize("change", [None, "program", "profile", "artifacts", "timeout"])
def test_retained_receipt_requires_identical_probe(tmp_path, monkeypatch, change):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    diagnostic = importlib.import_module("nas_diagnostic")
    arguments = dict(name="owned-preflight", program="print('original')", profile="antares",
                     timeout=90, secrets=(), artifacts=("resource-probe.json",))
    definition = Pipeline(
        id="leroy-nas-diagnostics", name="Owned probe", enabled=False, profile="antares",
        timeout=150, source={"kind": "diagnostic", "scenario": "owned-preflight"},
        steps=[Step(id="probe", name="owned-preflight", command=["python", "-c", arguments["program"]],
                    timeout=90, artifacts=["resource-probe.json"])],
    )
    path = tmp_path / "definition.json"
    path.write_text(definition.model_dump_json(indent=2))
    receipt = tmp_path / "run-id.json"
    receipt.write_text('{"id":"previous-successful-run"}')
    before = (path.read_bytes(), receipt.read_bytes())
    if change:
        arguments[change] = {"program": "print('different-image')", "profile": "graphato",
                             "artifacts": (), "timeout": 120}[change]
        with pytest.raises(AssertionError):
            diagnostic.validate_retained_probe(tmp_path, **arguments)
    else:
        diagnostic.validate_retained_probe(tmp_path, **arguments)
    assert (path.read_bytes(), receipt.read_bytes()) == before

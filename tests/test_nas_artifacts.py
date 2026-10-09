"""The Windows evidence collector must retain long Playwright resource paths."""

import hashlib
import importlib.util
import sys
from pathlib import Path

import httpx
import pytest


def test_collect_long_playwright_artifact(tmp_path, monkeypatch):
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location("nas_artifact_collector", scripts / "compare_nas_job.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    data = b"preserved trace resource"
    item = {
        "id": "artifact", "step_id": "browsers",
        "name": "test-results/playwright/" + "scenario-" * 12 + "/traces/resources/" + "a" * 64 + ".jpeg",
        "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
    }
    calls = []

    def serve(request):
        calls.append(request.url.path)
        return httpx.Response(200, content=data)

    folder = tmp_path / ("comparison-" * 5)
    with httpx.Client(base_url="http://evidence.test", transport=httpx.MockTransport(serve)) as api:
        module.collect_artifacts(api, {"artifacts": [item]}, folder)
        # Resuming a collection verifies and reuses the identical local bytes.
        module.collect_artifacts(api, {"artifacts": [item]}, folder)
        assert calls == ["/api/artifacts/artifact"]
        with pytest.raises(AssertionError):
            module.collect_artifacts(api, {"artifacts": [{**item, "name": "../outside"}]}, folder)
    assert sys.platform != "win32" or len(str(folder / "leroy-artifacts" / "browsers" / item["name"])) > 260

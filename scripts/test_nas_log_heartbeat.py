"""Verify continuous log delivery and lease survival under observed NAS load."""

import json

from nas_diagnostic import execute
from nas_followup_support import production_build
from nas_ssh import ROOT

PROGRAM = r'''
import json,pathlib,time
started=time.monotonic()
for sequence in range(120):
 print('LEROY_LOG_PROBE '+json.dumps({'sequence':sequence,'elapsed':time.monotonic()-started}),flush=True)
 time.sleep(1)
pathlib.Path('log-probe.json').write_text(json.dumps({'messages':120,'elapsed':time.monotonic()-started}))
'''


def main():
    deployment = json.loads((ROOT / "test-results/nas-parity/followup/log-heartbeat-deployment.json").read_text())
    assert deployment["readiness"]
    before = production_build()
    folder, run = execute("log-heartbeat-under-load", PROGRAM, timeout=240,
                          artifacts=["log-probe.json"], profile="antares")
    rows = [json.loads(line.split("LEROY_LOG_PROBE ", 1)[1])
            for line in (folder / "console.log").read_text().splitlines() if line.startswith("LEROY_LOG_PROBE ")]
    assert [row["sequence"] for row in rows] == list(range(120))
    payload = json.loads((folder / "leroy-artifacts/probe/log-probe.json").read_text())
    assert payload["messages"] == len(rows) and payload["elapsed"] >= 120
    report = {"passed": True, "run": run["id"], "messages": len(rows),
              "duration_seconds": payload["elapsed"], "controller_image": deployment["image"],
              "production_before": before, "production_after": production_build(),
              "scope": "Continuous real log uploads and worker heartbeats; no competing compiler or synthetic host load",
              "lease_or_pipeline_deadlines_changed": False}
    (folder / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()

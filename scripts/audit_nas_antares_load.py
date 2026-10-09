"""Record production CI overlap with completed Antares comparisons, read-only."""

import argparse
import json
import re
from datetime import datetime, timezone

from nas_ssh import ROOT, run_script

PROGRAM = r"""
import json,pathlib,subprocess,xml.etree.ElementTree as ET
info=json.loads(subprocess.check_output(['docker','inspect','jenkins'],text=True,timeout=20))[0]
mount=next(item for item in info['Mounts'] if item['Destination']=='/var/jenkins_home')
home=pathlib.Path(mount['Source']).resolve(strict=True)
root=(home/'jobs/graphato-ci').resolve(strict=True)
assert root.is_relative_to(home)
latest=int((root/'nextBuildNumber').read_text())-1
rows=[]
for number in range(max(1,latest-99),latest+1):
 path=root/'builds'/str(number)/'build.xml'
 assert path.resolve().is_relative_to(root)
 if not path.is_file():
  rows.append({'number':number,'unavailable':True});continue
 assert path.stat().st_size<16*1024*1024
 try:tree=ET.parse(path).getroot()
 except ET.ParseError:
  rows.append({'number':number,'unavailable':True});continue
 start=int(tree.findtext('startTime') or tree.findtext('timestamp'))
 duration=int(tree.findtext('duration') or 0)
 completed=tree.findtext('completed')=='true'
 rows.append({'number':number,'started_ms':start,'duration_ms':duration,
              'completed':completed,'result':tree.findtext('result')})
print(json.dumps({'latest_number':latest,'builds':rows}))
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True)
    candidate = parser.parse_args().candidate
    assert re.fullmatch("[a-f0-9]{40}", candidate)
    folder = ROOT / "test-results/nas-parity/followup/candidates/antares" / candidate
    state = json.loads((folder / "comparison.json").read_text())
    assert state["commit"] == candidate
    jenkins = state["jenkins"]
    assert not jenkins["building"] and jenkins["result"] and jenkins["duration"] > 0
    windows = {"jenkins": {
        "build": jenkins["number"],
        "started_ms": jenkins["timestamp"],
        "finished_ms": jenkins["timestamp"] + jenkins["duration"],
    }}
    leroy_path = folder / "leroy-run.json"
    if leroy_path.exists():
        leroy = json.loads(leroy_path.read_text())
        assert leroy["commit"] == candidate and leroy["finished_at"]
        windows["leroy"] = {"run": leroy["id"], **{
            name + "_ms": int(datetime.fromisoformat(leroy[name + "_at"]).timestamp() * 1000)
            for name in ("started", "finished")
        }}
    response = run_script(
        "python3 - <<'PY'\n" + PROGRAM + "\nPY\n", ROOT / ".local/nas-ssh.json",
        sudo=True, timeout=60,
    )
    if response.returncode:
        raise RuntimeError(response.stderr[-1500:])
    production = json.loads(response.stdout)
    rows = production["builds"]
    available = [row for row in rows if not row.get("unavailable")]
    first_start = min(window["started_ms"] for window in windows.values())
    covered = (rows[0]["number"] == 1 or any(row["started_ms"] <= first_start for row in available))
    covered = covered and len(available) == len(rows)
    now = datetime.now(timezone.utc)
    for window in windows.values():
        overlaps = []
        for row in available:
            end = (row["started_ms"] + row["duration_ms"] if row["completed"] else int(now.timestamp() * 1000))
            overlap = min(window["finished_ms"], end) - max(window["started_ms"], row["started_ms"])
            if overlap > 0:
                overlaps.append({"production_build": row["number"], "overlap_ms": overlap})
        window["production_ci_overlaps"] = overlaps
    report = {
        "candidate": candidate, "captured_at": now.isoformat(), "read_only": True,
        "scope": "Production graphato-ci build intervals only; not continuous compiler activity or all NAS load",
        "history_covers_test_windows": covered, "windows": windows, "production": production,
        "both_engines_collected": "leroy" in windows,
        "no_observed_production_ci_overlap": covered and all(
            not window["production_ci_overlaps"] for window in windows.values()
        ),
    }
    path = folder / "production-overlap.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key != "production"}))


if __name__ == "__main__":
    main()

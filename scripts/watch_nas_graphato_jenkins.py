"""Collect explicitly numbered candidate builds from the owned Jenkins volume.

This watcher never starts or retries a job. It reads the build files directly so
long target-host suites do not add HTTP or log serialization load to Jenkins.
"""

import argparse
import json
import subprocess
import sys
import time

from nas_candidate_paths import comparison_source
from nas_ssh import ROOT, run_script

PROGRAM = r"""
import json,pathlib,re,xml.etree.ElementTree as ET
assert pathlib.Path('/volume1/docker/leroy-nas-parity/.leroy-owned').is_file()
root=pathlib.Path('/volume1/@docker/volumes/leroy-nas-parity_engine/_data/volumes/jenkins-parity-aligned-home/_data')
rows={}
for job,number in BUILDS.items():
 path=root/'jobs'/job/'builds'/str(number)
 if not (path/'build.xml').exists():
  rows[job]={'number':number,'started':False}
  continue
 try: tree=ET.parse(path/'build.xml').getroot()
 except ET.ParseError:
  rows[job]={'number':number,'started':True,'building':True}
  continue
 stages=[]
 if (path/'log').is_file():
  with (path/'log').open('rb') as stream:
   stream.seek(max(0,(path/'log').stat().st_size-65536))
   text=stream.read().decode(errors='replace')
  stages=re.findall(r'\[Pipeline\] \{ \(([^)]+)\)',text)
 rows[job]={'number':number,'started':True,'building':tree.findtext('completed')!='true',
  'result':tree.findtext('result'),'stage':stages[-1] if stages else None}
print(json.dumps(rows))
"""


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--builds", required=True, help="JSON mapping of job names to recorded build numbers")
    args = parser.parse_args()
    _, folder = comparison_source("graphato-ci", args.candidate)
    builds = json.loads((ROOT / args.builds).read_text())
    allowed = {
        "graphato-bootstrap-host",
        "graphato-ci",
        "graphato-release-acceptance",
        "graphato-postdeploy-web",
        "graphato-postdeploy-quality",
    }
    assert builds and set(builds) <= allowed
    assert all(type(number) is int and number > 0 for number in builds.values())
    previous, collected = None, set()
    deadline = time.monotonic() + 9 * 3600
    while time.monotonic() < deadline:
        response = run_script(
            "python3 - <<'PY'\nBUILDS=" + repr(builds) + "\n" + PROGRAM + "\nPY\n",
            ROOT / ".local/nas-ssh.json",
            sudo=True,
            timeout=60,
        )
        if response.returncode:
            raise RuntimeError(response.stderr[-1500:])
        rows = json.loads(response.stdout)
        if rows != previous:
            print(json.dumps(rows), flush=True)
            previous = rows
        for job, state in rows.items():
            if not state.get("started") or state.get("building") or job in collected:
                continue
            assert state.get("result"), "Completed build has no result"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/collect_nas_jenkins_evidence.py"),
                    job,
                    "--build",
                    str(state["number"]),
                    "--candidate",
                    args.candidate,
                ],
                check=True,
            )
            collected.add(job)
        complete = len(collected) == len(builds)
        ci_failed = "graphato-ci" in collected and rows["graphato-ci"]["result"] != "SUCCESS"
        parent_finished_without_children = "graphato-release-acceptance" in collected and any(
            not state.get("started") for state in rows.values()
        )
        no_running = not any(state.get("building") for state in rows.values())
        if complete or ((ci_failed or parent_finished_without_children) and no_running):
            report = {"candidate": args.candidate, "builds": rows, "collected": sorted(collected)}
            label = "bootstrap" if set(builds) == {"graphato-bootstrap-host"} else "release"
            (folder.parent / ("jenkins-" + label + "-watch.json")).write_text(
                json.dumps(report, indent=2) + "\n"
            )
            assert complete and all(state["result"] == "SUCCESS" for state in rows.values()), report
            return
        time.sleep(45)
    raise TimeoutError("Candidate suites did not finish; no build was retried or cancelled")


if __name__ == "__main__":
    main()

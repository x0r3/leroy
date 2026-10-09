"""Read the owned Jenkins evidence through an authorized Leroy diagnostic worker."""

import argparse
import base64
import hashlib
import json
import shutil
from pathlib import PurePosixPath

from collect_nas_jenkins_evidence import PROGRAM as COLLECT
from nas_candidate_paths import comparison_source
from nas_diagnostic import execute
from nas_ssh import ROOT
from watch_nas_graphato_jenkins import PROGRAM as WATCH

JENKINS_ID = "29e75d9173c95db4f448ac038f2593e1f556e7eb2bf49bde68cba911526f3226"


def in_container(program):
    return program.replace(
        "assert pathlib.Path('/volume1/docker/leroy-nas-parity/.leroy-owned').is_file()\n", ""
    ).replace(
        "/volume1/@docker/volumes/leroy-nas-parity_engine/_data/volumes/jenkins-parity-aligned-home/_data",
        "/var/jenkins_home",
    )


PROGRAM = r"""
import json,pathlib,subprocess,time
info=json.loads(subprocess.check_output(['docker','inspect','jenkins-parity'],text=True))[0]
assert info['Id']==EXPECTED_ID and info['State']['Running']
output=pathlib.Path('evidence');output.mkdir(exist_ok=True)
previous=None;collected=set();deadline=time.monotonic()+8*3600
def read(script):
 return json.loads(subprocess.check_output(['docker','exec','jenkins-parity','python3','-c',script],text=True,timeout=90))
while time.monotonic()<deadline:
 rows=read('BUILDS='+repr(BUILDS)+'\n'+WATCH)
 if rows!=previous:print(json.dumps(rows),flush=True);previous=rows
 for job,state in rows.items():
  if not state.get('started') or state.get('building') or job in collected:continue
  evidence=read('JOB='+repr(job)+'\nNUMBER='+repr(state['number'])+'\n'+COLLECT)
  assert not evidence['build']['building']
  (output/(job+'.json')).write_text(json.dumps(evidence))
  collected.add(job)
 complete=len(collected)==len(BUILDS)
 ci_failed='graphato-ci' in collected and rows['graphato-ci']['result']!='SUCCESS'
 parent_finished_without_children='graphato-release-acceptance' in collected and any(not state.get('started') for state in rows.values())
 no_running=not any(state.get('building') for state in rows.values())
 if complete or ((ci_failed or parent_finished_without_children) and no_running):break
 time.sleep(45)
else:raise TimeoutError('Read-only Jenkins observation expired; no job was cancelled')
report={'candidate':CANDIDATE,'builds':rows,'collected':sorted(collected),'read_only':True,'jenkins_container_id':EXPECTED_ID,
 'complete':complete,'all_successful':complete and all(state['result']=='SUCCESS' for state in rows.values())}
(output/'watch.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report),flush=True)
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--builds", required=True)
    args = parser.parse_args()
    _, candidate = comparison_source("graphato-ci", args.candidate)
    numbers = json.loads((ROOT / args.builds).read_text())
    assert set(numbers) == {
        "graphato-ci",
        "graphato-release-acceptance",
        "graphato-postdeploy-web",
        "graphato-postdeploy-quality",
    }
    assert all(type(number) is int and number > 0 for number in numbers.values())
    values = {
        "EXPECTED_ID": JENKINS_ID,
        "CANDIDATE": args.candidate,
        "BUILDS": numbers,
        "WATCH": in_container(WATCH),
        "COLLECT": in_container(COLLECT),
    }
    assert "/volume1" not in values["WATCH"] and "/volume1" not in values["COLLECT"]
    program = "\n".join(key + "=" + repr(value) for key, value in values.items()) + "\n" + PROGRAM
    folder, run = execute(
        "jenkins-evidence-" + args.candidate[:12],
        program,
        timeout=9 * 3600,
        artifacts=["evidence/**"],
        poll_seconds=15,
    )
    archive = folder / "leroy-artifacts/probe/evidence"
    report = json.loads((archive / "watch.json").read_text())
    for job in report["collected"]:
        source, destination = comparison_source(job, args.candidate)
        evidence = json.loads((archive / (job + ".json")).read_text())
        state = evidence["build"]
        assert state["number"] == numbers[job] and not state["building"]
        assert source["commit"] in state["checkout_revisions"]
        pair_path = destination / "pair.json"
        pair = (
            json.loads(pair_path.read_text())
            if pair_path.exists()
            else {
                "pipeline": job,
                "commit": source["commit"],
                "parameters": json.loads((destination / "prepared.json").read_text())["parameters"],
                "application_patches_applied": True,
                "complete": False,
            }
        )
        assert pair.get("jenkins", {}).get("number", numbers[job]) == numbers[job]
        pair.update(
            jenkins=state,
            jenkins_evidence_source="read-only owned Jenkins via Leroy diagnostic",
            jenkins_evidence_run=run["id"],
        )
        for name in ["jenkins-console.log", f"jenkins-{numbers[job]}-console.log"]:
            (destination / name).write_text(evidence["console"], encoding="utf-8")
        target = destination / f"jenkins-{numbers[job]}-artifacts"
        for item in evidence["artifacts"]:
            content = item.pop("content", None)
            item["copied_locally"] = content is not None
            if content is None:
                continue
            path = PurePosixPath(item["name"])
            assert not path.is_absolute() and ".." not in path.parts
            data = base64.b64decode(content, validate=True)
            assert len(data) == item["size"] and hashlib.sha256(data).hexdigest() == item["sha256"]
            output = target.joinpath(*path.parts)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(data)
        (destination / f"jenkins-{numbers[job]}-artifact-index.json").write_text(
            json.dumps(evidence["artifacts"], indent=2) + "\n"
        )
        pair_path.write_text(json.dumps(pair, indent=2) + "\n")
    shutil.copyfile(archive / "watch.json", candidate.parent / "jenkins-release-watch-via-leroy.json")
    print(json.dumps(report), flush=True)
    assert report["all_successful"], "Collected actual failures; inspect the candidate receipts"


if __name__ == "__main__":
    main()

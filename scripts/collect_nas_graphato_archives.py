"""Retrieve the exact archived Jenkins suite bundles through the owned test worker."""

import argparse
import base64
import hashlib
import json

from nas_candidate_paths import comparison_source
from nas_diagnostic import execute
from watch_nas_graphato_via_leroy import JENKINS_ID

READER = r"""
import base64,hashlib,json,pathlib,xml.etree.ElementTree as ET
root=pathlib.Path('/evidence');rows=[]
for item in EXPECTED:
 build=root/'jobs'/item['job']/'builds'/str(item['number'])
 tree=ET.parse(build/'build.xml').getroot()
 assert tree.findtext('completed')=='true' and tree.findtext('result')==item['result']
 assert item['result'] in {'SUCCESS','FAILURE'}
 path=build/'archive'/item['name']
 assert path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root)
 assert path.stat().st_size==item['size'] and 0<item['size']<16*1024**2
 raw=path.read_bytes();assert hashlib.sha256(raw).hexdigest()==item['sha256']
 rows.append({**item,'content':base64.b64encode(raw).decode()})
print(json.dumps(rows))
"""

PROGRAM = r"""
import json,pathlib,subprocess
info=json.loads(subprocess.check_output(['docker','inspect','jenkins-parity'],text=True))[0]
assert info['Id']==EXPECTED_ID and not info['State']['Running']
(mount,)=[m for m in info['Mounts'] if m['Destination']=='/var/jenkins_home']
assert mount['Type']=='volume' and mount['Name']=='jenkins-parity-aligned-home'
raw=subprocess.check_output(['docker','run','--rm','--pull=never','--read-only','--network','none',
 '--memory','128m','--cpus','0.5','--pids-limit','64','--cap-drop','ALL','--mount',
 'type=volume,source='+mount['Name']+',target=/evidence,readonly','--entrypoint','python3',
 'leroy-job:nas-parity','-c','EXPECTED='+repr(EXPECTED)+'\n'+READER],timeout=120)
rows=json.loads(raw);assert len(rows)==len(EXPECTED)
pathlib.Path('jenkins-suite-bundles.json').write_bytes(raw)
print('Read and hashed the completed suite bundles from the stopped isolated Jenkins volume.')
"""


def collect(candidate):
    _, ci = comparison_source("graphato-ci", candidate)
    expected, destinations, availability = [], {}, {}
    for suite in ("web", "quality"):
        job = "graphato-postdeploy-" + suite
        folder = ci.parent / job
        pair = json.loads((folder / "pair.json").read_text())
        assert pair["commit"] == candidate and pair["jenkins"]["result"] in {"SUCCESS", "FAILURE"}
        assert not pair["jenkins"]["building"]
        number = pair["jenkins"]["number"]
        index_path = folder / f"jenkins-{number}-artifact-index.json"
        index = json.loads(index_path.read_text())
        name = f"target/postdeploy-{suite}/artifacts.tar.gz"
        items = [row for row in index if row["name"] == name]
        if not items:
            assert pair["jenkins"]["result"] == "FAILURE", "A successful suite must archive its bundle"
            availability[suite] = {"build": number, "result": "FAILURE", "bundle_archived": False,
                                   "reason": "No suite bundle in the recorded original artifact index"}
            continue
        (item,) = items
        availability[suite] = {"build": number, "result": pair["jenkins"]["result"], "bundle_archived": True}
        destination = folder / f"jenkins-{number}-artifacts" / name
        destinations[job] = destination, index_path
        if destination.exists():
            raw = destination.read_bytes()
            assert len(raw) == item["size"] and hashlib.sha256(raw).hexdigest() == item["sha256"]
        else:
            expected.append({"job": job, "number": number, "result": pair["jenkins"]["result"],
                             **{k: item[k] for k in ("name", "size", "sha256")}})
    report = ci.parent / "jenkins-suite-bundles-collection.json"
    report.write_text(json.dumps(availability, indent=2) + "\n")
    if not expected:
        return
    values = {"EXPECTED_ID": JENKINS_ID, "EXPECTED": expected, "READER": READER}
    program = "\n".join(k + "=" + repr(v) for k, v in values.items()) + "\n" + PROGRAM
    compile(program, "owned-jenkins-archive-reader", "exec")
    compile(READER, "bounded-read-only-volume-reader", "exec")
    diagnostic, run = execute(
        "graphato-jenkins-suite-bundles-" + candidate[:12], program,
        timeout=180, artifacts=["jenkins-suite-bundles.json"],
    )
    rows = json.loads((diagnostic / "leroy-artifacts/probe/jenkins-suite-bundles.json").read_text())
    assert [{k: row[k] for k in expected[0]} for row in rows] == expected
    for row in rows:
        raw = base64.b64decode(row["content"], validate=True)
        assert len(raw) == row["size"] and hashlib.sha256(raw).hexdigest() == row["sha256"]
        destination, index_path = destinations[row["job"]]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
        index = json.loads(index_path.read_text())
        for item in index:
            if item["name"] == row["name"]:
                item.update(copied_locally=True, collection_run=run["id"])
        index_path.write_text(json.dumps(index, indent=2) + "\n")
    print(f"{len(rows)} original Jenkins suite bundles copied and their recorded SHA-256 values verified.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True)
    collect(parser.parse_args().candidate)

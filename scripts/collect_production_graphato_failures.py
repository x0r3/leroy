"""Copy bounded existing failure archives, preserving their hashes and source identity."""

import base64
import hashlib
import json
import tarfile
from datetime import datetime, timezone

from nas_ssh import ROOT, run_script
from stage_nas_production_graphato import COMMIT

PROGRAM = r'''
import base64,hashlib,json,pathlib,xml.etree.ElementTree as ET
root=pathlib.Path('/volume1/docker/jenkins/jobs').resolve(strict=True);rows={}
for suite in ('web','quality'):
 job='graphato-postdeploy-'+suite;build=root/job/'builds'/'11'
 assert build.resolve().is_relative_to(root)
 tree=ET.parse(build/'build.xml').getroot()
 assert tree.findtext('completed')=='true' and tree.findtext('result')=='FAILURE'
 archive=build/'archive'/'target'/('postdeploy-'+suite);files=[]
 for name in ('result.json','cancellation.json','artifacts.tar.gz'):
  path=archive/name;assert not path.is_symlink() and path.resolve().is_relative_to(archive.resolve())
  size=path.stat().st_size;assert size<=2*1024**2
  data=path.read_bytes()
  if name=='result.json':assert json.loads(data)['commit']==COMMIT
  files.append({'name':name,'size':size,'sha256':hashlib.sha256(data).hexdigest(),'content':base64.b64encode(data).decode()})
 rows[suite]={'job':job,'build':11,'result':'FAILURE','files':files}
print(json.dumps({'read_only':True,'production_modified':False,'commit':COMMIT,'suites':rows}))
'''


def main():
    folder = ROOT / "test-results/nas-parity/followup/production-source-review/failed-groups"
    folder.mkdir(exist_ok=True)
    destination = folder / "collection.json"
    assert not destination.exists(), "No implicit repetition"
    result = run_script("python3 - <<'PY'\nCOMMIT=" + repr(COMMIT) + "\n" + PROGRAM + "\nPY\n", ROOT / ".local/nas-ssh.json", sudo=True, timeout=45)
    assert result.returncode == 0, "Read-only failure collection failed"
    record = json.loads(result.stdout)
    for suite, row in record["suites"].items():
        archive = folder / suite
        archive.mkdir(exist_ok=True)
        for item in row["files"]:
            content = base64.b64decode(item.pop("content"), validate=True)
            assert len(content) == item["size"] and hashlib.sha256(content).hexdigest() == item["sha256"]
            (archive / item["name"]).write_bytes(content)
        with tarfile.open(archive / "artifacts.tar.gz") as bundle:
            members = bundle.getmembers()
            assert len(members) <= 2000 and sum(member.size for member in members) <= 64 * 1024**2
            row["bundle_members"] = [{"name": member.name, "size": member.size, "regular_file": member.isfile()} for member in members]
    record["at"] = datetime.now(timezone.utc).isoformat()
    destination.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({"read_only": True, "commit": COMMIT,
                      "bundle_members": {suite: row["bundle_members"] for suite, row in record["suites"].items()}}))


if __name__ == "__main__":
    main()

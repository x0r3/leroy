"""Inventory only archived Graphato failures; never read credentials or change jobs."""

import json
from datetime import datetime, timezone

from nas_ssh import ROOT, run_script

PROGRAM = r'''
import json,pathlib,xml.etree.ElementTree as ET
root=pathlib.Path('/volume1/docker/jenkins/jobs').resolve(strict=True)
rows={}
for job in ('graphato-postdeploy-web','graphato-postdeploy-quality'):
 build=root/job/'builds'/'11';assert build.resolve().is_relative_to(root)
 tree=ET.parse(build/'build.xml').getroot()
 assert tree.findtext('completed')=='true' and tree.findtext('result')=='FAILURE'
 archive=build/'archive';files=[]
 for path in sorted(archive.rglob('*')):
  if not path.is_file():continue
  assert not path.is_symlink() and path.resolve().is_relative_to(archive.resolve())
  files.append({'name':path.relative_to(archive).as_posix(),'size':path.stat().st_size})
  assert len(files)<=2000
 rows[job]={'build':11,'result':'FAILURE','artifacts':files}
print(json.dumps({'read_only':True,'production_modified':False,'jobs':rows}))
'''


def main():
    folder = ROOT / "test-results/nas-parity/followup/production-source-review"
    destination = folder / "production-failure-artifact-inventory.json"
    assert not destination.exists(), "No implicit repetition"
    result = run_script("python3 - <<'PY'\n" + PROGRAM + "\nPY\n", ROOT / ".local/nas-ssh.json", sudo=True, timeout=45)
    assert result.returncode == 0, "Read-only archive inventory failed"
    record = {**json.loads(result.stdout), "at": datetime.now(timezone.utc).isoformat()}
    destination.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record))


if __name__ == "__main__":
    main()

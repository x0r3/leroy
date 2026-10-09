"""Read only the owned Graphato comparison job states and console tails."""

import json
import sys

from deploy_nas_parity import CREDENTIALS
from nas_ssh import ROOT, run_script

PROGRAM = r"""
import json,pathlib,re,xml.etree.ElementTree as ET
assert pathlib.Path('/volume1/docker/leroy-nas-parity/.leroy-owned').is_file()
root=pathlib.Path('/volume1/@docker/volumes/leroy-nas-parity_engine/_data/volumes/jenkins-parity-aligned-home/_data/jobs')
rows=[]
for job in ['graphato-ci','graphato-release-acceptance','graphato-postdeploy-web','graphato-postdeploy-quality']:
 folder=root/job/'builds'/'1'
 if not (folder/'build.xml').exists():
  rows.append({'pipeline':job,'started':False})
  continue
 tree=ET.parse(folder/'build.xml').getroot()
 row={'pipeline':job,'started':True,'completed':tree.findtext('completed')=='true','result':tree.findtext('result'),'timestamp':int(tree.findtext('timestamp'))}
 log=folder/'log'
 with log.open('rb') as stream:
  stream.seek(max(0,log.stat().st_size-20000))
  tail=stream.read().decode('utf-8',errors='replace')
 row['console_tail']=re.sub(r'\x1b\[8m.*?\x1b\[0m','',tail)[-1600:]
 rows.append(row)
print(json.dumps(rows))
"""


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    response = run_script("python3 - <<'PY'\n" + PROGRAM + "PY\n", CREDENTIALS, sudo=True, timeout=30)
    if response.returncode:
        raise RuntimeError(response.stderr[-1000:])
    rows = json.loads(response.stdout)
    (ROOT / "test-results/nas-parity/graphato-jenkins-progress.json").write_text(
        json.dumps(rows, indent=2) + "\n", encoding="utf-8"
    )
    for row in rows:
        print(row["pipeline"], row.get("result") or ("running" if row["started"] else "not started"))
        if row["started"] and not row["completed"]:
            print(row["console_tail"])


if __name__ == "__main__":
    main()

"""Capture non-secret pressure metrics for the owned nested test daemon only."""

import json

from deploy_nas_parity import CREDENTIALS
from nas_ssh import ROOT, run_script

PROGRAM = r"""
import json,pathlib,subprocess,time
assert pathlib.Path('/volume1/docker/leroy-nas-parity/.leroy-owned').is_file()
id=subprocess.check_output(['docker','inspect','--format','{{.Id}}','leroy-nas-parity-docker-1'],text=True).strip()
root=pathlib.Path('/sys/fs/cgroup/system.slice','docker-'+id+'.scope')
def values(name):return dict(line.split() for line in (root/name).read_text().splitlines())
out={'at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
for name in ('memory.current','memory.max','memory.swap.current','memory.swap.max'):
 out[name]=int((root/name).read_text())
out['memory.events']=values('memory.events')
out['memory.pressure']=(root/'memory.pressure').read_text().splitlines()
out['io.pressure']=(root/'io.pressure').read_text().splitlines()
out['host_available_kib']=int(next(l.split()[1] for l in pathlib.Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))
rows=[]
for proc in pathlib.Path('/proc').glob('[0-9]*'):
 try:
  group=(proc/'cgroup').read_text()
  if root.name not in group:continue
  fields=dict(line.split(':',1) for line in (proc/'status').read_text().splitlines())
  rss=int(fields.get('VmRSS','0 kB').split()[0]);swap=int(fields.get('VmSwap','0 kB').split()[0])
  if rss+swap>150000:rows.append({'pid':proc.name,'name':fields['Name'].strip(),'rss_kib':rss,'swap_kib':swap})
 except (FileNotFoundError,PermissionError,ProcessLookupError):pass
out['large_owned_processes']=sorted(rows,key=lambda r:r['rss_kib']+r['swap_kib'],reverse=True)
print(json.dumps(out))
"""


def main():
    response = run_script("python3 - <<'PY'\n" + PROGRAM + "PY\n", CREDENTIALS, sudo=True, timeout=30)
    if response.returncode:
        raise RuntimeError(response.stderr[-1000:])
    row = json.loads(response.stdout)
    path = ROOT / "test-results/nas-parity/graphato-resource-observations.jsonl"
    with path.open("a") as stream:
        stream.write(json.dumps(row) + "\n")
    print(json.dumps(row))


if __name__ == "__main__":
    main()

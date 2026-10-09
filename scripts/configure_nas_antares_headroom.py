"""Increase only the owned test daemon's RAM cap after its recorded browser OOM."""

import json
from datetime import datetime, timezone

from nas_followup_support import remote, wait_production_jobs
from nas_gitea_target import idle
from nas_ssh import ROOT

CANDIDATE = "8607cfd438c7645012bf0482a5da83acb122d6dd"


def main():
    folder = ROOT / "test-results/nas-parity/followup/candidates/antares" / CANDIDATE
    marker = folder / "headroom-applied.json"
    assert not marker.exists(), "No implicit resource reapplication"
    result = json.loads((folder / "focused-browsers-full-matrix-1g.json").read_text())
    assert result["helpers_removed"] and not result["passed"] and result["production_jobs_unchanged"]
    events = json.loads((folder / "full-matrix-1g-oom-events.json").read_text())
    assert events and all(row["Actor"]["Attributes"]["name"] == "antares-browser-probe-8607cfd438c7-full-matrix-1g" for row in events)
    production = wait_production_jobs()
    idle()
    program = r'''
import hashlib,json,pathlib,subprocess
root=pathlib.Path('/volume1/docker/leroy-nas-parity');assert (root/'.leroy-owned').is_file()
info=json.loads(subprocess.check_output(['docker','inspect','leroy-nas-parity-docker-1'],text=True,timeout=20))[0]
assert info['Id']=='7d029e17dc28b04ec41ac927360062f057c97564227c62e7e01a50a4938b5a00'
assert info['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity'
old={k:info['HostConfig'][k] for k in ['Memory','MemorySwap','NanoCpus']}
assert old=={'Memory':3584*1024**2,'MemorySwap':6144*1024**2,'NanoCpus':6_000_000_000}
available=int(next(line.split()[1] for line in pathlib.Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:')))*1024
assert available>=2*1024**3,'Retain at least one GiB available headroom beyond the one-GiB cap increase'
prefix=['docker','exec','leroy-nas-parity-docker-1','docker']
assert subprocess.check_output(prefix+['inspect','jenkins-parity','--format','{{.State.Running}}'],text=True,timeout=20).strip()=='false'
assert not subprocess.check_output(prefix+['ps','--filter','label=io.leroy.runner=runner-nas-parity','-q'],text=True,timeout=20).strip()
names=subprocess.check_output(prefix+['ps','--format','{{.Names}}'],text=True,timeout=20).splitlines()
assert not any(n.startswith('antares-') for n in names)
path=root/'compose.yaml';before=path.read_bytes();text=before.decode()
assert text.count('mem_limit: 3584m')==1
updated=text.replace('mem_limit: 3584m','mem_limit: 4608m',1).encode()
backup=root/'compose-before-antares-headroom.yaml';assert not backup.exists();backup.write_bytes(before)
subprocess.run(['docker','update','--memory','4608m','--memory-swap','6144m',info['Id']],check=True,capture_output=True,timeout=30)
current=json.loads(subprocess.check_output(['docker','inspect',info['Id']],text=True,timeout=20))[0]
actual={k:current['HostConfig'][k] for k in old}
assert actual=={**old,'Memory':4608*1024**2} and current['State']['Running']
path.write_bytes(updated)
subprocess.run(['docker','compose','config','--quiet'],cwd=root,check=True,capture_output=True,timeout=30)
print(json.dumps({'daemon_id':info['Id'],'before':old,'after':actual,'host_mem_available_before':available,
 'compose_before_sha256':hashlib.sha256(before).hexdigest(),'compose_after_sha256':hashlib.sha256(updated).hexdigest(),
 'daemon_restarted':False,'swap_and_cpu_caps_unchanged':True}))
'''
    report = json.loads(remote(program, timeout=150))
    path = ROOT / "infra/nas/compose.yaml"
    text = path.read_text()
    assert text.count("mem_limit: 3584m") == 1
    path.write_text(text.replace("mem_limit: 3584m", "mem_limit: 4608m", 1))
    report.update(at=datetime.now(timezone.utc).isoformat(), production_before=production,
                  production_modified=False, full_ci_acceptance=False)
    marker.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in ("before", "after", "host_mem_available_before", "daemon_restarted")}), flush=True)


if __name__ == "__main__":
    main()

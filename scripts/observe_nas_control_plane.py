"""Sample only the three owned control services during the frozen NAS workload."""

import argparse
import json
from datetime import datetime, timezone

from compare_existing_host_nas_graphato import FOLDER
from nas_ssh import ROOT, run_script

PROGRAM = r'''
import json,pathlib,subprocess
root=pathlib.Path('/volume1/docker/leroy-nas-parity');assert (root/'.leroy-owned').is_file()
rows={}
for name,expected in EXPECTED.items():
 info=json.loads(subprocess.check_output(['docker','inspect','leroy-nas-parity-'+name+'-1'],text=True))[0]
 assert info['Id']==expected.get('after_id',expected.get('id')) and info['Image']==expected['image']
 assert info['State']['Running']
 relative=pathlib.Path('/proc',str(info['State']['Pid']),'cgroup').read_text().strip().split('::',1)[1]
 group=pathlib.Path('/sys/fs/cgroup',relative.lstrip('/'))
 rows[name]={'container_id':info['Id'],'image':info['Image'],'running':True,
  'health':info['State'].get('Health',{}).get('Status'),'oom_killed':info['State']['OOMKilled'],
  'restart_count':info['RestartCount'],'started_at':info['State']['StartedAt'],
  'memory_events':dict(line.split() for line in (group/'memory.events').read_text().splitlines()),
  'memory_current_bytes':int((group/'memory.current').read_text()),
  'swap_current_bytes':int((group/'memory.swap.current').read_text()),
  'swap_max_bytes':int((group/'memory.swap.max').read_text()),
  'memory_low_bytes':int((group/'memory.low').read_text()),
  'memory_pressure':(group/'memory.pressure').read_text().splitlines(),
  'io_pressure':(group/'io.pressure').read_text().splitlines()}
 assert rows[name]['swap_max_bytes']==0 and rows[name]['memory_low_bytes']==expected['memory_low_bytes']
print(json.dumps({'services':rows,'read_only':True,'production_modified':False}))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fresh', action='store_true', help='Observe the fresh comparison without creating its later scenario folder')
    args = parser.parse_args()
    proof = ROOT / 'test-results/nas-parity/followup/control-plane-residency-deployment.json'
    expected = json.loads(proof.read_text())['services']
    program = 'EXPECTED=' + repr(expected) + '\n' + PROGRAM
    result = run_script("python3 - <<'PY'\n" + program + '\nPY\n',
                        ROOT / '.local/nas-ssh.json', sudo=True, timeout=60)
    assert result.returncode == 0, result.stderr[-1000:]
    record = json.loads(result.stdout)
    record['at'] = datetime.now(timezone.utc).isoformat()
    folder = FOLDER.parents[1] if args.fresh else FOLDER
    assert folder.is_dir()
    with (folder / 'control-plane-observations.jsonl').open('a') as target:
        target.write(json.dumps(record) + '\n')
    print(json.dumps({'at': record['at'], 'services': {name: {
        key: row[key] for key in ('health', 'restart_count', 'swap_current_bytes', 'memory_events')}
        for name, row in record['services'].items()}}))


if __name__ == '__main__':
    main()

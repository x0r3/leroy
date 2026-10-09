"""Capture public resource limits and Rust event counts, without commands or secrets."""

import argparse
import json
import re

from nas_ssh import ROOT
from prepare_nas_vm import guest

PROGRAM = r'''
import collections,json,pathlib,re,subprocess,time
assert pathlib.Path('/var/lib/leroy-vm/ready').is_file()
path=pathlib.Path('/var/lib/graphato-host/postdeploy/results')/COMMIT/'quality/server-test.log'
events=[]
if path.exists():
 assert path.stat().st_size<=64*1024**2
 for line in path.read_text(errors='replace').splitlines():
  try:value=json.loads(line)
  except ValueError:continue
  if isinstance(value,dict):events.append(value)
terminal=[row for row in events if row.get('type')=='test' and row.get('event') in {'ok','failed','ignored'}]
expected=sum(row['test_count'] for row in events if row.get('type')=='suite' and row.get('event')=='started')
ids=subprocess.check_output(['docker','ps','-q','--filter','label=com.docker.compose.project'],text=True).split()
containers=json.loads(subprocess.check_output(['docker','inspect',*ids],text=True)) if ids else []
rows=[]
for container in containers:
 labels=container['Config']['Labels'];project=labels.get('com.docker.compose.project','')
 if not re.fullmatch(r'graphato-ci-check-[a-f0-9]{12}',project):continue
 service=labels['com.docker.compose.service']
 assert service in {'server-test-build','server-tests','postgres-test'}
 host=container['HostConfig'];pid=container['State']['Pid']
 row={'service':service,'project':project,'image':container['Image'],
  'limits':{key:host[key] for key in ['Memory','MemorySwap','NanoCpus','PidsLimit']},
  'environment':[value for value in container['Config']['Env'] if value.startswith(('RUST_TEST_THREADS=','CARGO_BUILD_JOBS='))],
  'oom_killed':container['State']['OOMKilled'],'restart_count':container['RestartCount']}
 relative=next(line.split('::',1)[1] for line in pathlib.Path('/proc',str(pid),'cgroup').read_text().splitlines() if line.startswith('0::'))
 cgroup=(pathlib.Path('/sys/fs/cgroup')/relative.lstrip('/')).resolve()
 assert cgroup.is_relative_to(pathlib.Path('/sys/fs/cgroup'))
 row['cgroup']={name:(cgroup/name).read_text().strip() for name in ['memory.current','memory.max','memory.swap.current','memory.swap.max','memory.events','cpu.stat']}
 rows.append(row)
print(json.dumps({'at':time.time(),'expected_so_far':expected,'terminal_so_far':len(terminal),
 'counts':dict(collections.Counter(row['event'] for row in terminal)),
 'failed_tests':[row['name'] for row in terminal if row['event']=='failed'],
 'subject_events':[{key:row[key] for key in ['name','event','exec_time'] if key in row}
  for row in terminal if row['name'].endswith('story_locks_allow_independent_merges_and_exclude_shared_publication')],
 'containers':rows,'read_only':True,'every_instant_observed':False}))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--round', type=int, choices=[1, 2], required=True)
    parser.add_argument('--engine', choices=['jenkins', 'leroy'], required=True)
    args = parser.parse_args()
    assert re.fullmatch('[a-f0-9]{40}', args.commit)
    folder = ROOT / 'test-results/nas-parity/followup/candidates/graphato' / args.commit
    folder /= 'controlled-groups/quality-server-test-round-' + str(args.round)
    assert (folder / (args.engine + '-start.json')).is_file()
    assert not (folder / (args.engine + '-target-after.json')).exists(), 'Do not attribute another engine to a completed run'
    data = guest('sudo python3 -B -', 'COMMIT=' + repr(args.commit) + '\n' + PROGRAM, timeout=45)
    value = json.loads(data)
    destination = folder / (args.engine + '-resource-observations.jsonl')
    assert destination.resolve().is_relative_to(ROOT.resolve())
    with destination.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(value) + '\n')
    print(json.dumps({key: value[key] for key in ['at', 'expected_so_far', 'terminal_so_far',
                                               'counts', 'failed_tests', 'subject_events']}), flush=True)


if __name__ == '__main__':
    main()

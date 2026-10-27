"""Stage a separately qualified Compose override before baseline services start."""

PROGRAM = r'''
import json,os,pathlib,subprocess
assert os.geteuid()==0 and pathlib.Path('/var/lib/leroy-vm/ready').is_file()
assert subprocess.check_output(['systemd-detect-virt'],text=True).strip()=='kvm'
ids=subprocess.check_output(['docker','ps','-aq','--filter','label=com.docker.compose.project=graphato-prod'],text=True).split()
assert len(ids)==4
rows=json.loads(subprocess.check_output(['docker','inspect',*ids],text=True))
assert not any(r['State']['Running'] for r in rows),'Stage init only before the clean baseline starts'
root=pathlib.Path('/var/lib/leroy-vm');assert root.resolve()==root
target=root/'postgres-init.override.json';expected={'services':{'postgres':{'init':True}}}
assert not target.is_symlink()
if target.exists():assert json.loads(target.read_text())==expected
else:
 with target.open('x') as stream:
  stream.write(json.dumps(expected)+'\n');stream.flush();os.fsync(stream.fileno())
 target.chmod(0o600)
print(json.dumps({'test_baseline_postgres_init_override_staged':True,
 'original_source_and_tests_modified':False,'original_ci_started':False}))
'''


PROOF = r'''
import json,pathlib,subprocess
p=pathlib.Path('/var/lib/leroy-vm/postgres-init.override.json')
ids=subprocess.check_output(['docker','ps','-aq','--filter','label=com.docker.compose.project=graphato-prod',
 '--filter','label=com.docker.compose.service=postgres'],text=True).split()
assert len(ids)==1
c=json.loads(subprocess.check_output(['docker','inspect',ids[0]],text=True))[0]
print(json.dumps({'override_present':p.exists(),'postgres_init':bool(c['HostConfig'].get('Init'))}))
'''

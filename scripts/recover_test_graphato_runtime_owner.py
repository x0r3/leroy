"""Use Graphato's existing crash recovery command in the owned test VM only."""

import json

from fetch_native_graphato_runtime import EVIDENCE
from nas_measurement_guard import begin, finish
from nas_ssh import ROOT
from nas_target_host_guard import begin as host_begin
from nas_target_host_guard import finish as host_finish
from prepare_nas_vm import guest

PROGRAM = r'''
import hashlib,json,pathlib,subprocess,types
assert pathlib.Path('/var/lib/leroy-vm/ready').is_file()
assert subprocess.check_output(['systemd-detect-virt'],text=True).strip()=='kvm'
manifest=pathlib.Path('/opt/graphato/current/manifest.json');data=manifest.read_bytes();m=json.loads(data)
assert m['commit']=='0ad540dd578033d45e4d0c25d89fbe57b32102a4'
assert m['runtimeImageId']=='sha256:6251c60f499e41e706613f931bf281ce52312b957d5a6a123cf4e27dd3242585'
module=types.ModuleType('owned_test_lifecycle')
exec(compile(LIFECYCLE,'original owned test lifecycle','exec'),module.__dict__);command=module.command()
assert command[command.index('--project-name')+1]=='graphato-prod'
ids=subprocess.check_output(['docker','ps','-aq','--filter','label=com.docker.compose.project=graphato-prod'],text=True).split()
rows=json.loads(subprocess.check_output(['docker','inspect',*ids],text=True));assert len(rows)==4
server,=[r for r in rows if r['Config']['Labels']['com.docker.compose.service']=='server']
logs=subprocess.run(['docker','logs','--tail','30',server['Id']],text=True,capture_output=True)
assert 'Previous runtime ownership is unresolved' in logs.stdout+logs.stderr
receipts=pathlib.Path('/var/lib/graphato-host/postdeploy/results')
def hashes():return {str(p.relative_to(receipts)):hashlib.sha256(p.read_bytes()).hexdigest() for p in receipts.rglob('result.json')}
before=hashes();operations=[]
def run(*args):
 r=subprocess.run([*command,*args],capture_output=True,timeout=240)
 operations.append({'operation':args[0],'exit_code':r.returncode,'stdout_sha256':hashlib.sha256(r.stdout).hexdigest(),'stderr_sha256':hashlib.sha256(r.stderr).hexdigest()})
 assert r.returncode==0,'Owned test runtime recovery operation failed; retained output hashes only'
run('stop','server','agent-test-worker','maintenance')
rows=json.loads(subprocess.check_output(['docker','inspect',*ids],text=True))
assert all(not r['State']['Running'] for r in rows if r['Config']['Labels']['com.docker.compose.service']!='postgres')
assert not subprocess.check_output(['docker','ps','-q','--filter','label=io.graphato.e2e.owner'],text=True).strip()
run('run','--rm','--no-deps','server','/usr/local/bin/graphato-server','--recover-runtime-ownership','--acknowledge-all-previous-owners-stopped')
run('up','-d','--wait','--wait-timeout','180')
rows=json.loads(subprocess.check_output(['docker','inspect',*ids],text=True))
assert all(r['State']['Running'] and r['State'].get('Health',{}).get('Status')=='healthy' for r in rows)
assert hashes()==before and manifest.read_bytes()==data
print(json.dumps({'recovered_after_verified_stop_of_all_owned_execution_services':True,'original_active_release_unchanged':True,'original_receipts_unchanged':True,'application_services_healthy':4,'operations':operations,'test_files_modified':False,'production_modified':False}))
'''


def main():
    path = EVIDENCE / 'runtime-owner-recovery.json'
    assert not path.exists(), 'Retain the first runtime recovery receipt'
    host_before = host_begin(EVIDENCE, 'runtime-owner-recovery')
    before = begin(EVIDENCE, 'runtime-owner-recovery')
    program = 'LIFECYCLE=' + repr((ROOT / 'infra/vm/graphato-lifecycle.py').read_text()) + '\n' + PROGRAM
    compile(program, 'owned Graphato crash recovery', 'exec')
    result = json.loads(guest('sudo python3 -B -', program, timeout=600))
    result.update({'target_host_qualification': host_finish(EVIDENCE, 'runtime-owner-recovery', host_before),
                   'production_qualification': finish(EVIDENCE, 'runtime-owner-recovery', before)})
    path.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'owned_test_runtime_owner_recovered': True, 'healthy_services': 4,
                      'original_receipts_unchanged': True, 'tests_modified': False}), flush=True)


if __name__ == '__main__':
    main()

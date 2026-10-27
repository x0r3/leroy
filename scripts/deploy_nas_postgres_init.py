"""Enable qualified orphan reaping only on the idle Leroy test database."""

import json
from datetime import datetime, timezone

import nas_release_vm as vm
from nas_gitea_target import idle
from nas_measurement_guard import begin, finish
from nas_ssh import ROOT

PROGRAM = r'''
import hashlib,json,os,pathlib,subprocess,time
root=pathlib.Path('/volume1/docker/leroy-nas-parity')
assert root.resolve()==root and (root/'.leroy-owned').is_file()
work=root/'postgres-init-deployment-20261014';assert not work.exists();work.mkdir(mode=0o700)
def call(args,timeout=30):
 r=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
 if r.returncode:raise RuntimeError('Scoped test database operation failed; output withheld')
 return r.stdout.strip()
def inspect(name):return json.loads(call(['docker','inspect','leroy-nas-parity-'+name+'-1']))[0]
def save(path,data):
 with path.open('xb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
 path.chmod(0o600)
before={name:inspect(name) for name in ('postgres','controller','runner','docker')}
assert all(c['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity' for c in before.values())
assert not before['postgres']['HostConfig'].get('Init')
assert all(c['State']['Running'] for c in before.values())
save(work/'containers-before.json',json.dumps(before).encode())
sql='SELECT json_build_object('+','.join("'"+t+"',(SELECT count(*) FROM "+t+")" for t in ('runs','steps','artifacts','pipelines'))+');'
def counts(identity):return json.loads(call(['docker','exec',identity,'psql','-X','-U','leroy','-d','leroy','-Atc',sql]))
counts_before=counts(before['postgres']['Id'])
save(work/'counts-before.json',json.dumps(counts_before).encode())
with (work/'database-before.dump').open('xb') as stream:
 r=subprocess.run(['docker','exec',before['postgres']['Id'],'pg_dump','-U','leroy','-d','leroy','-Fc'],
  stdout=stream,stderr=subprocess.PIPE,timeout=120)
 assert r.returncode==0,'Backup failed; output withheld'
 stream.flush();os.fsync(stream.fileno())
(work/'database-before.dump').chmod(0o600)
override=root/'compose.override.yaml';raw=override.read_bytes();save(work/'compose.override.before',raw)
compose=['docker','compose','--project-directory',str(root)]
original=json.loads(call(compose+['config','--format','json']))
value=json.loads(raw);value['services']['postgres']['init']=True
candidate=work/'compose.override.candidate.json';save(candidate,(json.dumps(value,indent=2)+'\n').encode())
normalized=json.loads(call(compose+['-f',str(root/'compose.yaml'),'-f',str(candidate),'config','--format','json']))
expected=json.loads(json.dumps(original));expected['services']['postgres']['init']=True
assert normalized==expected,'Only the test database init setting may change'
temporary=root/'compose.override.postgres-init.partial';save(temporary,candidate.read_bytes())
os.chown(temporary,override.stat().st_uid,override.stat().st_gid);os.chmod(temporary,override.stat().st_mode&0o777)
os.replace(temporary,override)
call(compose+['up','-d','--no-deps','--pull','never','postgres'],timeout=150)
deadline=time.monotonic()+120
while time.monotonic()<deadline:
 current=inspect('postgres')
 if current['State']['Running'] and current['State'].get('Health',{}).get('Status')=='healthy':break
 time.sleep(2)
else:raise RuntimeError('Test database health incomplete; preserve backed-up staging')
previous=before['postgres']
assert current['HostConfig']['Init'] is True and current['Image']==previous['Image']
assert sorted(current['Mounts'],key=lambda x:x['Destination'])==sorted(previous['Mounts'],key=lambda x:x['Destination'])
assert sorted(current['Config']['Env'])==sorted(previous['Config']['Env'])
for key in ('Cmd','Entrypoint','User','WorkingDir','Healthcheck'):assert current['Config'].get(key)==previous['Config'].get(key)
host,old=json.loads(json.dumps(current['HostConfig'])),json.loads(json.dumps(previous['HostConfig']))
old['Init']=True
for row in (host,old):
 if row.get('Binds'):row['Binds']=sorted(row['Binds'])
assert host==old,'Runtime settings changed beyond Init'
assert {n:v['IPAddress'] for n,v in current['NetworkSettings']['Networks'].items()}=={n:v['IPAddress'] for n,v in previous['NetworkSettings']['Networks'].items()}
assert counts(current['Id'])==counts_before
for name in ('controller','runner','docker'):
 now=inspect(name);old=before[name]
 assert now['Id']==old['Id'] and now['State']['Pid']==old['State']['Pid'] and now['RestartCount']==old['RestartCount']
 assert now['State']['Running'] and now['Config']==old['Config'] and now['HostConfig']==old['HostConfig']
assert json.loads(call(compose+['config','--format','json']))==expected
with (work/'database-before.dump').open('rb') as stream:backup_sha=hashlib.file_digest(stream,'sha256').hexdigest()
proof={'postgres_init_enabled':True,'same_database_image_volumes_resources_environment_and_address':True,
 'database_table_counts_unchanged':counts_before,'controller_runner_and_dind_processes_unchanged':True,
 'database_backup_sha256':backup_sha,'original_postgres_id':previous['Id'],'new_postgres_id':current['Id'],
 'new_postgres_healthy':True,'source_and_tests_changed':False,'production_modified':False,'production_ready':False}
save(work/'deployment-proof.json',(json.dumps(proof,indent=2)+'\n').encode())
print(json.dumps(proof))
'''


def main():
    folder = ROOT / 'test-results/nas-parity/followup/offline-forensics-20261014'
    qualification = json.loads((folder / 'postgres-init-probe.json').read_text())
    assert qualification['controlled_orphan_reproduction_passed']
    idle()
    assert not vm.state()['State']['Running']
    boundary = begin(folder, 'test-postgres-init')
    try:
        value = json.loads(vm.remote(PROGRAM, sudo=True, timeout=360))
        value['at'] = datetime.now(timezone.utc).isoformat()
        (folder / 'postgres-init-deployment.json').write_text(json.dumps(value, indent=2) + '\n')
        print(json.dumps(value))
    finally:
        finish(folder, 'test-postgres-init', boundary)


if __name__ == '__main__':
    main()

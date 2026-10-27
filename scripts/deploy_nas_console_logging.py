"""Install the qualified controller console fix in the idle owned test stack."""

import argparse
import json

from nas_gitea_target import idle
from nas_measurement_guard import begin, finish
from nas_ssh import ROOT, run_script
from qualify_nas_console_logging import FOLDER, OLD

PROGRAM = r'''
import hashlib,json,os,pathlib,subprocess,time
root=pathlib.Path('/volume1/docker/leroy-nas-parity');assert root.resolve()==root and (root/'.leroy-owned').is_file()
context=root/'console-queue-deployment-20261017';assert not context.exists();context.mkdir(mode=0o700)
def call(args,timeout=30):
 r=subprocess.run(args,capture_output=True,timeout=timeout)
 assert r.returncode==0,'Inspect protected deployment evidence before another operation'
 return r.stdout
def inspect(name):return json.loads(call(['docker','inspect',name]))[0]
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def snapshot():
 out={}
 for n in ('controller','postgres','runner','docker'):
  c=inspect('leroy-nas-parity-'+n+'-1');assert c['State']['Running']
  config={k:v for k,v in c['Config'].items() if k not in ('Image','Cmd','Labels','Hostname')}
  out[n]={'id':c['Id'],'image':c['Image'],'pid':c['State']['Pid'],'oom':c['State']['OOMKilled'],
   'config_sha256':digest(config),'host_config_sha256':digest(c['HostConfig']),
   'mounts_sha256':digest(sorted(c['Mounts'],key=lambda m:m['Destination'])),
   'command':c['Config']['Cmd'],'networks':sorted(c['NetworkSettings']['Networks'])}
 return out
proof=json.loads((root/'console-queue-qualification-20261017/verification.json').read_text())
assert proof['candidate_image']==CANDIDATE and proof['source_sha256']==SOURCES and proof['all_passed']
for mode in ('legacy','bounded'):
 p=root/'console-pipe-20261017'/('pipe'+mode)
 value=json.loads((p/'result.json').read_text());cleanup=json.loads((p/'cleanup.json').read_text())
 assert cleanup['temporary_controllers_runners_and_jobs_removed'] and not cleanup['warnings']
 assert value['run']['status']==('succeeded' if mode=='bounded' else 'interrupted')
 assert all(r['direct_sql']['ok'] for r in value['samples'])
 if mode=='bounded':assert all(r['api_live']['ok'] for r in value['samples']) and value['verified_artifacts']
 else:assert any(not r['api_live']['ok'] for r in value['samples'])
before=snapshot();assert before['controller']['image']==OLD
assert not inspect('leroy-nas-release-target-vm')['State']['Running']
inner=['docker','exec',before['docker']['id'],'docker']
assert call(inner+['inspect','jenkins-parity','--format','{{.State.Running}}']).strip()==b'false'
assert not call(inner+['ps','-q','--filter','label=io.leroy.runner=runner-nas-parity']).strip()
assert not call(['docker','ps','-q','--filter','label=io.leroy.control-probe']).strip()
def seven():
 for n in ('paperless','sonarr','radarr','sabnzbd','plex','yt-downloader-service','mail-ingest-service'):
  c=inspect(n);assert c['State']['Running'] and c['State'].get('Health',{}).get('Status') in (None,'healthy')
seven()
sql="select json_build_object('runs',(select count(*) from runs),'steps',(select count(*) from steps),'artifacts',(select count(*) from artifacts),'pipelines',(select count(*) from pipelines),'users',(select count(*) from users),'active',(select count(*) from runs where status in ('queued','running','waiting')))"
def db():return json.loads(call(['docker','exec','-e','PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=10000',before['postgres']['id'],'psql','-XqAt','-U','leroy','-d','leroy','-c',sql]))
state=db();assert state['active']==0
dump=context/'leroy.dump'
with dump.open('xb') as out:
 r=subprocess.run(['docker','exec',before['postgres']['id'],'pg_dump','-Fc','-U','leroy','-d','leroy'],stdout=out,stderr=subprocess.PIPE,timeout=90)
 assert r.returncode==0;out.flush();os.fsync(out.fileno())
dump.chmod(0o600)
config={}
for name in ('compose.yaml','compose.override.yaml','config/leroy.toml','config/runner.toml','config/controller.env'):
 path=root/name;data=path.read_bytes();config[name]=hashlib.sha256(data).hexdigest()
 dest=context/'backup'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data);dest.chmod(0o600)
(context/'before.json').write_text(json.dumps({'services':before,'database':state,'configuration_sha256':config},indent=2)+'\n')
call(['docker','tag',CANDIDATE,'leroy-controller:nas-parity'])
call(['docker','compose','--project-directory',str(root),'-f',str(root/'compose.yaml'),'-f',str(root/'compose.override.yaml'),'up','-d','--no-deps','--force-recreate','controller'],timeout=150)
until=time.monotonic()+120
while time.monotonic()<until:
 c=inspect('leroy-nas-parity-controller-1')
 if c['State']['Running'] and c['State'].get('Health',{}).get('Status')=='healthy':break
 time.sleep(2)
else:raise RuntimeError('Corrected controller did not become healthy; inspect owned deployment')
after=snapshot();assert after['controller']['image']==CANDIDATE and not after['controller']['oom']
assert after['controller']['command']==['sh','-c','alembic upgrade head && exec python -m leroy.server']
for n in before:
 if n!='controller':assert before[n]==after[n]
 else:
  for k in ('config_sha256','host_config_sha256','mounts_sha256','networks'):assert before[n][k]==after[n][k],k
assert db()==state
assert config=={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in config}
modules=json.loads(call(['docker','exec',after['controller']['id'],'python','-c',"import hashlib,json,pathlib,leroy.console_logging,leroy.server;print(json.dumps({pathlib.Path(m.__file__).name:hashlib.sha256(pathlib.Path(m.__file__).read_bytes()).hexdigest() for m in (leroy.console_logging,leroy.server)}))"]))
assert modules=={n:SOURCES[n] for n in ('console_logging.py','server.py')}
seven()
value={'previous_services':before,'services':after,'controller_image':CANDIDATE,'previous_controller_image':OLD,
 'source_sha256':modules,'database_backup_sha256':hashlib.sha256(dump.read_bytes()).hexdigest(),
 'configuration_files_unchanged':True,'database_rows_unchanged':True,'only_controller_recreated':True,
 'runner_worker_database_and_dind_unchanged':True,'seven_services_healthy':True,
 'lease_deadlines_changed':False,'graphato_sources_tests_fixture_limits_changed':False,
 'production_modified':False,'production_ready':False,'production_cutover':False}
(context/'deployment-proof.json').write_text(json.dumps(value,indent=2)+'\n')
print(json.dumps(value))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collect-existing', action='store_true', help='Verify the known installation without recreating anything')
    collect = parser.parse_args().collect_existing
    proof = json.loads((FOLDER / 'qualification-proof.json').read_text())
    for mode in ('legacy', 'bounded'):
        folder = FOLDER / ('worker-' + mode)
        assert (folder / 'result.json').is_file()
        measure = json.loads((folder / ('production-measurement-qualification-console-pipe-' + mode + '.json')).read_text())
        assert measure['native_jenkins_quiet_window_verified']
    idle()
    folder = FOLDER / 'deployment'
    if collect:
        assert folder.is_dir() and not (folder / 'collection-program.py').exists()
        before, = [p.name for p in folder.glob('production-measurement-before-console-queue-deployment-*.json')]
    else:
        folder.mkdir()
        before = begin(folder, 'console-queue-deployment')
    program = ('OLD=' + repr(OLD) + '\nCANDIDATE=' + repr(proof['candidate_image'])
               + '\nSOURCES=' + repr(proof['source_sha256']) + '\n' + PROGRAM)
    if collect:
        # The retained hash was recovered exactly by permuting only Env order.
        # All values and all other fields must still compare equal. No deployment
        # command is part of this collection program.
        definitions = PROGRAM.split("proof=json.loads", 1)[0].replace(
            "context=root/'console-queue-deployment-20261017';assert not context.exists();context.mkdir(mode=0o700)",
            "context=root/'console-queue-deployment-20261017';assert context.is_dir()")
        restore = r'''
prior=json.loads((context/'before.json').read_text());before=prior['services'];state=prior['database'];config=prior['configuration_sha256'];dump=context/'leroy.dump'
recovered=json.loads((context/'recovered-before-config.json').read_text())
assert digest(recovered)==before['controller']['config_sha256']
actual=inspect('leroy-nas-parity-controller-1')
current={k:v for k,v in actual['Config'].items() if k not in ('Image','Cmd','Labels','Hostname')}
recovered['Env']=sorted(recovered['Env']);current['Env']=sorted(current['Env']);assert current==recovered
old_host=json.loads((context/'recovered-before-host-config.json').read_text())
assert digest(old_host)==before['controller']['host_config_sha256']
current_host=actual['HostConfig']
for host in (old_host,current_host):
 host['Binds']=sorted(host['Binds']);host['Mounts']=sorted(host['Mounts'],key=lambda m:json.dumps(m,sort_keys=True))
assert old_host==current_host
def db():return json.loads(call(['docker','exec','-e','PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=10000',before['postgres']['id'],'psql','-XqAt','-U','leroy','-d','leroy','-c',SQL]))
def seven():
 for n in ('paperless','sonarr','radarr','sabnzbd','plex','yt-downloader-service','mail-ingest-service'):
  c=inspect(n);assert c['State']['Running'] and c['State'].get('Health',{}).get('Status') in (None,'healthy')
'''
        sql = "select json_build_object('runs',(select count(*) from runs),'steps',(select count(*) from steps),'artifacts',(select count(*) from artifacts),'pipelines',(select count(*) from pipelines),'users',(select count(*) from users),'active',(select count(*) from runs where status in ('queued','running','waiting')))"
        tail = 'after=snapshot()' + PROGRAM.split('after=snapshot()', 1)[1]
        tail = tail.replace("('config_sha256','host_config_sha256','mounts_sha256','networks')", "('mounts_sha256','networks')")
        constants = 'OLD=' + repr(OLD) + '\nCANDIDATE=' + repr(proof['candidate_image']) + '\nSOURCES=' + repr(proof['source_sha256']) + '\nSQL=' + repr(sql) + '\n'
        program = constants + definitions + restore + tail
    (folder / ('collection-program.py' if collect else 'program.py')).write_text(program)
    result = run_script("python3 - <<'PY'\n" + program + '\nPY\n', ROOT / '.local/nas-ssh.json', sudo=True, timeout=480)
    (folder / ('collection-stdout.log' if collect else 'stdout.log')).write_text(result.stdout)
    (folder / ('collection-stderr.log' if collect else 'stderr.log')).write_text(result.stderr)
    assert result.returncode == 0, 'Inspect retained deployment before another change'
    value = json.loads(result.stdout)
    (folder / 'deployment-proof.json').write_text(json.dumps(value, indent=2) + '\n')
    finish(folder, 'console-queue-deployment', before)
    print(json.dumps({'controller_image': value['controller_image'], 'only_controller_recreated': True}))


if __name__ == '__main__':
    main()

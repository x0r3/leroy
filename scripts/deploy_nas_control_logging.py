"""Apply verified diagnostic logging isolation to the idle owned NAS stack only."""

import argparse
import hashlib
import json
import tarfile
from datetime import datetime, timezone

from diagnose_nas_control_latency import FOLDER
from nas_gitea_target import idle
from nas_measurement_guard import begin, finish
from nas_ssh import ROOT, run_script, upload_file

PROGRAM = r"""
import hashlib,json,os,pathlib,re,subprocess,tarfile,time,tomllib
root=pathlib.Path('/volume1/docker/leroy-nas-parity');assert root.resolve()==root and (root/'.leroy-owned').is_file()
context=root/'control-logging-20261012';assert not context.exists();context.mkdir(mode=0o700)
def call(args,timeout=30,payload=None):
 try:r=subprocess.run(args,input=payload,text=True,capture_output=True,timeout=timeout)
 except subprocess.TimeoutExpired:raise RuntimeError('Bounded deployment operation timed out') from None
 if r.returncode:raise RuntimeError('Bounded deployment operation failed: '+str(r.returncode))
 return r.stdout.strip()
def inspect(name):return json.loads(call(['docker','inspect',name]))[0]
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def snapshot():
 rows={}
 for s in ('postgres','controller','runner','docker'):
  c=inspect('leroy-nas-parity-'+s+'-1');assert c['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity'
  rows[s]={'image':c['Image'],'environment_sha256':digest(sorted(c['Config']['Env'])),
   'command_sha256':digest({k:c['Config'].get(k) for k in ('Cmd','Entrypoint','WorkingDir','User')}),
   'resources':{k:c['HostConfig'][k] for k in ('Memory','MemorySwap','MemoryReservation','NanoCpus','CpuShares','Privileged')},
   'mounts':sorted([{k:m[k] for k in ('Type','Source','Destination','RW')} for m in c['Mounts']],key=lambda m:m['Destination']),
   'network_names':sorted(c['NetworkSettings']['Networks']),'logging':c['HostConfig']['LogConfig'],
   'running':c['State']['Running'],'health':c['State'].get('Health',{}).get('Status')}
 return rows
before=snapshot();assert all(row['running'] for row in before.values())
assert before['runner']['image']==EXPECTED_RUNNER_IMAGE
assert not inspect('leroy-nas-release-target-vm')['State']['Running']
assert not call(['docker','ps','-q','--filter','label=io.leroy.control-probe'])
inner=['docker','exec','leroy-nas-parity-docker-1','docker']
assert call(inner+['inspect','jenkins-parity','--format','{{.State.Running}}'])=='false'
assert not call(inner+['ps','-q','--filter','label=io.leroy.runner=runner-nas-parity'])
source_image=tomllib.loads((root/'config/runner.toml').read_text())['profiles']['graphato']['image']
assert source_image.startswith('sha256:')
worker_before=json.loads(call(inner+['image','inspect',source_image]))[0]['Id']
nested_before={}
for id in call(inner+['ps','-q']).split():
 c=json.loads(call(inner+['inspect',id]))[0]
 nested_before[c['Name'].lstrip('/')]=c['Id']
configuration={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ('compose.override.yaml','config/leroy.toml','config/runner.toml','config/controller.env')}
sql="select json_build_object('runs',(select count(*) from runs),'steps',(select count(*) from steps),'artifacts',(select count(*) from artifacts),'pipelines',(select count(*) from pipelines),'users',(select count(*) from users),'active',(select count(*) from runs where status in ('queued','running','waiting')),'fsync',current_setting('fsync'),'synchronous_commit',current_setting('synchronous_commit'),'full_page_writes',current_setting('full_page_writes'))"
def database_state():return json.loads(call(['docker','exec','-e','PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=10000','leroy-nas-parity-postgres-1','psql','-XqAt','-U','leroy','-d','leroy','-c',sql]))
db_before=database_state();assert db_before['active']==0 and all(db_before[k]=='on' for k in ('fsync','synchronous_commit','full_page_writes'))
dump=context/'leroy.dump'
with dump.open('xb') as out:
 r=subprocess.run(['docker','exec','leroy-nas-parity-postgres-1','pg_dump','-Fc','-U','leroy','-d','leroy'],stdout=out,stderr=subprocess.PIPE,timeout=90)
 assert r.returncode==0;out.flush();os.fsync(out.fileno())
dump.chmod(0o600)
base=root/'compose.yaml';old_bytes=base.read_bytes();old_stat=base.stat()
(context/'compose.before.yaml').write_bytes(old_bytes)
text=old_bytes.decode();pattern=r'(?m)^([ \t]*)options: \{max-size: "?10m"?, max-file: "?3"?\}$'
new_text,count=re.subn(pattern,r'\1options: {max-size: "10m", max-file: "3", mode: "non-blocking", max-buffer-size: "4m"}',text)
assert count==1,'Inspect the actual Compose logging anchor rather than guessing its format'
candidate=context/'compose.candidate.yaml';candidate.write_text(new_text)
config=json.loads(call(['docker','compose','--project-directory',str(root),'-f',str(candidate),'-f',str(root/'compose.override.yaml'),'config','--format','json']))
assert all(config['services'][s]['logging']['options']['mode']=='non-blocking' for s in before)
with tarfile.open(root/'control-logging-20261012.tar') as archive:
 members=archive.getmembers();assert {m.name for m in members}==set(EXPECTED_MODULES)
 for member in members:
  assert member.isfile() and member.size<1024**2
  data=archive.extractfile(member).read();assert hashlib.sha256(data).hexdigest()==EXPECTED_MODULES[member.name]
  (context/member.name).write_bytes(data)
backup_tag='leroy-runner:nas-parity-before-logging-20261012';new_tag='leroy-runner:nas-parity-logging-20261012'
for tag in (backup_tag,new_tag):
 assert subprocess.run(['docker','image','inspect',tag],capture_output=True,timeout=20).returncode!=0
call(['docker','tag',before['runner']['image'],backup_tag])
target=call(['docker','exec','leroy-nas-parity-runner-1','python','-c','import pathlib,leroy.runner;print(pathlib.Path(leroy.runner.__file__).parent)'])
assert target.startswith('/usr/local/lib/python3.') and target.endswith('/site-packages/leroy')
call(['docker','build','--network=none','--pull=false','-t',new_tag,'-f','-',str(context)],timeout=240,
 payload='FROM '+backup_tag+'\nCOPY runner.py worker.py '+target+'/\n')
new_image=json.loads(call(['docker','image','inspect',new_tag]))[0]
old_image=json.loads(call(['docker','image','inspect',before['runner']['image']]))[0]
assert new_image['Config']==old_image['Config'] and new_image['RootFS']['Layers'][:-1]==old_image['RootFS']['Layers']
(context/'before.json').write_text(json.dumps({'services':before,'database':db_before,'nested':nested_before,'configuration_sha256':configuration},indent=2)+'\n')
candidate.chmod(old_stat.st_mode&0o777);os.chown(candidate,old_stat.st_uid,old_stat.st_gid)
with candidate.open('rb') as f:os.fsync(f.fileno())
os.replace(candidate,base)
call(['docker','tag',new_image['Id'],'leroy-runner:nas-parity'])
call(['docker','compose','--project-directory',str(root),'-f',str(base),'-f',str(root/'compose.override.yaml'),'up','-d','--force-recreate','postgres','docker','controller','runner'],timeout=180)
deadline=time.monotonic()+150
while time.monotonic()<deadline:
 after=snapshot()
 if all(row['running'] for row in after.values()) and all(after[s]['health']=='healthy' for s in ('postgres','controller','docker')):break
 time.sleep(2)
else:raise RuntimeError('Owned stack did not regain health')
for name,id in nested_before.items():
 assert json.loads(call(inner+['inspect',id]))[0]['Name'].lstrip('/')==name
 if call(inner+['inspect',id,'--format','{{.State.Running}}'])!='true':call(inner+['start',id])
for s in before:
 for key in ('environment_sha256','command_sha256','resources','mounts','network_names'):assert after[s][key]==before[s][key],s+' runtime changed'
 assert after[s]['logging']['Type']==before[s]['logging']['Type']=='json-file'
 assert after[s]['logging']['Config']=={**before[s]['logging']['Config'],'mode':'non-blocking','max-buffer-size':'4m'}
 if s!='runner':assert after[s]['image']==before[s]['image']
assert database_state()==db_before
assert configuration=={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in configuration}
assert worker_before==json.loads(call(inner+['image','inspect',source_image]))[0]['Id']
assert call(inner+['inspect','jenkins-parity','--format','{{.State.Running}}'])=='false'
code="import hashlib,pathlib,json,leroy.runner,leroy.worker;print(json.dumps({m.__name__.split('.')[-1]+'.py':hashlib.sha256(pathlib.Path(m.__file__).read_bytes()).hexdigest() for m in (leroy.runner,leroy.worker)}))"
assert json.loads(call(['docker','exec','leroy-nas-parity-runner-1','python','-c',code]))==EXPECTED_MODULES
proof={'previous_services':before,'services':after,'database_before_and_after':db_before,'module_sha256':EXPECTED_MODULES,
 'runner_image':new_image['Id'],'old_runner_image_retained':True,'database_backup_sha256':hashlib.sha256(dump.read_bytes()).hexdigest(),
 'original_compose_sha256':hashlib.sha256(old_bytes).hexdigest(),'new_compose_sha256':hashlib.sha256(base.read_bytes()).hexdigest(),
 'configuration_other_than_diagnostic_logging_unchanged':True,'nested_service_ids_retained':nested_before,
 'original_controller_postgres_daemon_and_worker_images_unchanged':True,'graphato_sources_tests_or_deadlines_changed':False,
 'worker_and_server_lease_deadlines_changed':False,'productive_services_modified':False}
(context/'deployment-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps(proof))
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    assert parser.parse_args().apply
    comparison = json.loads((FOLDER / "mode-comparison.json").read_text(encoding="utf-8"))
    assert (
        comparison["synthetic_fault_class_proven"]
        and comparison["nonblocking_original_job_status"] == "succeeded"
    )
    idle()
    folder = FOLDER / "deployment"
    folder.mkdir(exist_ok=True)
    assert not (folder / "started.json").exists(), "Inspect an uncertain installation before retrying"
    before = begin(folder, "control-logging-deployment")
    expected = {
        name + ".py": hashlib.sha256((ROOT / "src/leroy" / (name + ".py")).read_bytes()).hexdigest()
        for name in ("runner", "worker")
    }
    archive = folder / "control-logging-20261012.tar"
    with tarfile.open(archive, "w") as bundle:
        for name in expected:
            bundle.add(ROOT / "src/leroy" / name, arcname=name)
    (folder / "started.json").write_text(
        json.dumps(
            {
                "at": datetime.now(timezone.utc).isoformat(),
                "production_guard_before": before,
                "module_sha256": expected,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    upload_file(archive, "/volume1/docker/leroy-nas-parity/" + archive.name, ROOT / ".local/nas-ssh.json")
    old = json.loads((FOLDER / "blocking-bounded/result.json").read_text(encoding="utf-8"))["runner_image"]
    program = "EXPECTED_MODULES=" + repr(expected) + "\nEXPECTED_RUNNER_IMAGE=" + repr(old) + "\n" + PROGRAM
    (folder / "program.py").write_text(program, encoding="utf-8")
    result = run_script(
        "python3 - <<'PY'\n" + program + "\nPY\n", ROOT / ".local/nas-ssh.json", sudo=True, timeout=780
    )
    (folder / "stdout.log").write_text(result.stdout, encoding="utf-8")
    (folder / "stderr.log").write_text(result.stderr, encoding="utf-8")
    finish(folder, "control-logging-deployment", before)
    assert result.returncode == 0, "Installation outcome must be inspected before another action"
    proof = json.loads(result.stdout)
    (folder / "deployment-proof.json").write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "runner_image": proof["runner_image"],
                "all_four_services_use_buffered_diagnostic_logging": True,
                "durable_database_and_worker_images_unchanged": True,
                "productive_services_modified": False,
            }
        )
    )


if __name__ == "__main__":
    main()

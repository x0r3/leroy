"""Compare original Soak checks with isolated/native runtime inputs in a fixed A/B/A sequence."""

import argparse
import json
import subprocess
from contextlib import closing

from compare_nas_antares import client
from nas_diagnostic import execute
from nas_ssh import ROOT
from nas_target_host_guard import begin as host_begin
from nas_target_host_guard import finish as host_finish

COMMIT = '0ad540dd578033d45e4d0c25d89fbe57b32102a4'
NAME = 'frozen-runtime-aba-' + COMMIT[:12]
NATIVE = ROOT / 'test-results/nas-parity/followup/native-browser-observations/web-18'

GUEST = r'''
import hashlib,importlib.util,json,os,pathlib,shutil,subprocess,tarfile,tempfile,time
assert pathlib.Path('/var/lib/leroy-vm/ready').is_file() and os.cpu_count()==4
release=pathlib.Path('/opt/graphato/current').resolve(strict=True)
assert release.parent==pathlib.Path('/opt/graphato/releases')
manifest_path=release/'manifest.json';original_manifest_bytes=manifest_path.read_bytes()
control=json.loads(original_manifest_bytes);assert control['commit']==COMMIT
assert control['runtimeImageId']==CONTROL_IMAGE and control['files']['verification-source.tar.gz']==SOURCE_SHA
with (release/'verification-source.tar.gz').open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==SOURCE_SHA
helper=release/'deployments/linux/host/postdeploy.py'
assert hashlib.sha256(helper.read_bytes()).hexdigest()==control['files']['deployments/linux/host/postdeploy.py']
spec=importlib.util.spec_from_file_location('unchanged_runtime_diagnosis',helper)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
original_state=module.STATE
def original_receipts():
 return {suite:(hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None)
  for suite in module.SUITES for p in [original_state/'results'/COMMIT/suite/'result.json']}
before=original_receipts()
assert not subprocess.check_output(['docker','ps','-q','--filter','label=io.graphato.e2e.owner'],text=True).strip()
directory=pathlib.Path('/var/lib/leroy-vm/diagnostics')/NAME;assert not directory.exists()
directory.mkdir(parents=True,mode=0o700);rows=[]
native=json.loads(json.dumps(NATIVE_MANIFEST));native['runtimeImageId']=NATIVE_IMAGE
assert native['commit']==COMMIT and native['files']['verification-source.tar.gz']==SOURCE_SHA
assert native['files']['deployments/linux/host/postdeploy.py']==control['files']['deployments/linux/host/postdeploy.py']
for case,chosen,server_sha in [('control-first',control,CONTROL_SERVER_SHA),('native',native,NATIVE_SERVER_SHA),('control-last',control,CONTROL_SERVER_SHA)]:
 case_root=directory/case;case_root.mkdir(mode=0o700)
 module.STATE=case_root/'private-postdeploy-state';module.STATE.mkdir(mode=0o700)
 reports=case_root/'reports';reports.mkdir(mode=0o700)
 pointer=module.STATE/'fixture-state.json';started=time.time();error_type=None
 with module.cancellation() as interrupted,module.host_lock(),tempfile.TemporaryDirectory(prefix='source-',dir=module.STATE) as source:
  source=pathlib.Path(source);module.source_extract(release/module.SOURCE_ARCHIVE,source)
  executor=module.Executor(source,reports/'browser-soak.log')
  if COPY_OWNED_BUILDER_DEFINITION:
   private_state=module.STATE
   try:
    module.STATE=pathlib.Path(OWNED_BUILDER_STATE)
    assert module.STATE.is_dir() and not module.STATE.is_symlink()
    verifier=module.Executor(source,reports/'owned-builder-validation.log')
    assert verifier.builder_definition()==module.BUILDER_OPTIONS
    verified_builder=verifier.builder_container();assert verified_builder is not None
    assert verified_builder['HostConfig']['Memory']==6*1024**3
   finally:module.STATE=private_state
   # Copy only the validated single-node definition, never Docker credentials.
   origin=pathlib.Path(OWNED_BUILDER_STATE)/'docker-config/buildx/instances'/module.BUILDER
   destination=module.STATE/'docker-config/buildx/instances'/module.BUILDER
   destination.parent.mkdir(parents=True,mode=0o700)
   shutil.copyfile(origin,destination);os.chmod(destination,0o600)
   assert executor.builder_definition()==module.BUILDER_OPTIONS
  ci=module.adapt_ci(source,release,chosen,executor);os.environ['CI_STATE_FILE']=str(pointer)
  ci.cleanup(pointer)
  name,action=next(row for row in module.check_steps(ci,executor,source,release,chosen,reports)['web'] if row[0]=='browser-soak')
  try:action()
  except (OSError,ValueError,KeyError,AssertionError,subprocess.SubprocessError) as error:error_type=type(error).__name__
  finally:
   interrupted['cleaning']=True
   ci.cleanup(pointer)
   if executor.builder_started:executor.run('docker','buildx','stop',module.BUILDER,timeout=60)
  assert not pointer.exists()
  assert not interrupted['requested'],'Retain an interrupted diagnostic; no implicit next sample'
 assert not subprocess.check_output(['docker','ps','-q','--filter','label=io.graphato.e2e.owner'],text=True).strip()
 result_path=reports/'browser-soak/open/results.json'
 # Preserve and stop a startup failure; never call it an executed Soak sample.
 assert result_path.is_file(),'Original browser test did not produce a case result'
 cases=json.loads(result_path.read_text());assert len(cases)==1 and cases[0]['id']=='soak'
 outcome=cases[0];provenance=json.loads((reports/'browser-soak/provenance.json').read_text())
 server=json.loads((reports/'browser-soak/server.json').read_text())
 assert provenance['runnerSource']=={'commit':COMMIT,'sourceArchiveSha256':SOURCE_SHA,'dirty':False}
 assert server['sourceCommit']==COMMIT and server['serverSha256']==server_sha
 assert server['serverBuild']['timestamp']==chosen['build']['timestamp']
 metrics=[]
 for line in (reports/'browser-soak.log').read_text(errors='replace').splitlines():
  try:value=json.loads(line[line.index('{'):])
  except ValueError:continue
  if isinstance(value,dict) and value.get('event')=='boundedSoak':metrics.append(value)
 if outcome['passed']:
  metric,=metrics;assert metric['tabs']==4 and metric['prompts']==120 and metric['durationSeconds']>=300
  assert metric['failedResponses']==0 and metric['statuses'].get('429',0)<metric['polls']/10
  assert metric['secondsSinceLastRateLimit'] is None or metric['secondsSinceLastRateLimit']>30
 row={'case':case,'passed':outcome['passed'],'started_at_epoch':started,'finished_at_epoch':time.time(),
  'runtime_image_id':chosen['runtimeImageId'],'server_sha256':server['serverSha256'],
  'build_timestamp':server['serverBuild']['timestamp'],'runtime_base_sha256':server['runtimeBaseSha256'],
  'browser_worker_image_id':provenance['workerImageId'],'source_archive_sha256':SOURCE_SHA,
  'docker_host':server['dockerHost'],'metrics':metrics,'case_result':outcome,
  'execution_error_type':error_type,'cleanup_complete':True,'application_and_test_files_modified':False}
 rows.append(row);(directory/'samples.json').write_text(json.dumps(rows,indent=2)+'\n')
 assert original_receipts()==before and manifest_path.read_bytes()==original_manifest_bytes
same_worker=len({row['browser_worker_image_id'] for row in rows})==1
output={'commit':COMMIT,'samples':rows,'fixed_sequence':['control-first','native','control-last'],
 'all_original_case_checks_executed':True,'same_browser_worker_image_all_samples':same_worker,
 'same_source_archive_all_samples':True,'original_receipts_before_and_after':before,
 'original_active_release_modified':False,'application_and_test_files_modified':False,
 'browser_observer_preload_used':False,'original_acceptance_result_replaced':False,
 'full_release_acceptance':False,'production_modified':False,'production_replacement_ready':False,
 'scope':'Original browser-soak actions with an explicit runtime input in private fresh fixtures; not a full release or engine parity claim'}
archive=directory/'runtime-pair-artifacts.tar.gz'
with tarfile.open(archive,'w:gz') as tar:
 for path in sorted(directory.rglob('*')):
  if not path.is_file() or not path.is_relative_to(directory) or path==archive:continue
  if not any(path.is_relative_to(directory/case/'reports') for case in output['fixed_sequence']):continue
  assert not path.is_symlink() and path.stat().st_size<=64*1024**2
  tar.add(path,arcname=path.relative_to(directory).as_posix(),recursive=False)
with archive.open('rb') as stream:output['artifact_archive_sha256']=hashlib.file_digest(stream,'sha256').hexdigest()
(directory/'runtime-pair-result.json').write_text(json.dumps(output,indent=2)+'\n')
print(json.dumps(output))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--owned-builder-definition', action='store_true')
    args = parser.parse_args()
    name = NAME + ('-owned-builder' if args.owned_builder_definition else '')
    original = json.loads((NATIVE / 'ci-23-manifest-observation.json').read_text())['manifest']
    loaded_path = NATIVE / 'runtime-loaded-in-test-vm.json'
    native_image = json.loads(loaded_path.read_text())['image_id'] if loaded_path.exists() else 'NOT_LOADED'
    assert args.prepare_only or native_image != 'NOT_LOADED'
    parameters = {'COMMIT': COMMIT, 'NAME': name, 'NATIVE_MANIFEST': original,
                  'NATIVE_IMAGE': native_image,
                  'COPY_OWNED_BUILDER_DEFINITION': args.owned_builder_definition,
                  'OWNED_BUILDER_STATE': '/var/lib/leroy-vm/diagnostics/frozen-soak-rate-proposal-0ad540dd5780/private-postdeploy-state',
                  'CONTROL_IMAGE': 'sha256:6251c60f499e41e706613f931bf281ce52312b957d5a6a123cf4e27dd3242585',
                  'SOURCE_SHA': original['files']['verification-source.tar.gz'],
                  'CONTROL_SERVER_SHA': '0f3f4ebb3ea557807528bdb9ee67f6d4cf489f63865d46016ece5ea5a272dfe4',
                  'NATIVE_SERVER_SHA': 'faab058b0006184428efe434cfaef40028b07b495d9c61b82cf719b9bcb27519'}
    guest_program = '\n'.join(key + '=' + repr(value) for key, value in parameters.items()) + '\n' + GUEST
    compile(guest_program, 'unchanged original Soak runtime diagnosis', 'exec')
    fetch = "import pathlib,shutil,sys\np=pathlib.Path('/var/lib/leroy-vm/diagnostics/" + name + "/runtime-pair-artifacts.tar.gz')\n"
    fetch += "assert p.is_file() and p.stat().st_size<256*1024**2\nwith p.open('rb') as f:shutil.copyfileobj(f,sys.stdout.buffer)\n"
    program = "import hashlib,json,pathlib,re,subprocess\nfrom leroy.actions import required,ssh_args\n"
    program += "command=ssh_args('graphato-vm','root',12225,required('BOOTSTRAP_KEY'),required('KNOWN_HOSTS'))\n"
    program += "r=subprocess.run([*command,'python3 -B -'],input=" + repr(guest_program) + ",text=True,capture_output=True,timeout=5400)\n"
    program += "if r.returncode:\n pathlib.Path('failure.json').write_text(json.dumps({'exit_code':r.returncode,'stdout_sha256':hashlib.sha256(r.stdout.encode()).hexdigest(),'stderr_sha256':hashlib.sha256(r.stderr.encode()).hexdigest(),'exception_types':re.findall(r'^([A-Za-z]+Error):',r.stderr,re.MULTILINE)},indent=2)+'\\n')\n raise SystemExit('Inspect the retained original-runtime diagnosis failure; no implicit retry')\n"
    program += "value=json.loads(r.stdout)\npathlib.Path('runtime-pair-result.json').write_text(json.dumps(value,indent=2)+'\\n')\n"
    program += "with pathlib.Path('runtime-pair-artifacts.tar.gz').open('wb') as stream:subprocess.run([*command,'python3 -B -'],input=" + repr(fetch.encode()) + ",stdout=stream,stderr=subprocess.PIPE,check=True,timeout=180)\n"
    program += "with pathlib.Path('runtime-pair-artifacts.tar.gz').open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==value['artifact_archive_sha256']\n"
    program += "print(json.dumps({'samples':[{key:r[key] for key in ['case','passed','browser_worker_image_id']} for r in value['samples']],'test_files_modified':False}),flush=True)\n"
    assert len(program) < 32768
    compile(program, 'NAS runtime-input diagnostic dispatcher', 'exec')
    if args.prepare_only:
        print(json.dumps({'prepared': True, 'test_files_modified': False, 'dispatcher_chars': len(program),
                          'nas_run_started': False, 'fixed_sequence': ['control-first', 'native', 'control-last']}))
        return
    folder = ROOT / 'test-results/nas-parity/followup' / name
    assert not folder.exists() or args.resume, 'Retain the first runtime-input diagnostic'
    checkout = ROOT / '.sources/frozen-master/graphato-0ad540dd5780'
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=checkout, text=True).strip() == COMMIT
    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=checkout)
    if not args.resume:
        folder.mkdir(parents=True)
        host_before = host_begin(folder, 'runtime-aba')
    with closing(client()) as api:
        previous = next(row['spec'] for row in api.get('/api/pipelines').json() if row['id'] == 'leroy-nas-diagnostics')
    try:
        _, run = execute(name, program, secrets=('graphato-bootstrap',), timeout=5460,
                         artifacts=('runtime-pair-result.json', 'runtime-pair-artifacts.tar.gz', 'failure.json'), profile='graphato')
    finally:
        with closing(client()) as api:
            api.put('/api/pipelines/leroy-nas-diagnostics', json=previous).raise_for_status()
    result_path = folder / 'leroy-artifacts/probe/runtime-pair-result.json'
    if not args.resume:
        host_finish(folder, 'runtime-aba', host_before)
    result = json.loads(result_path.read_text())
    assert result['application_and_test_files_modified'] is False and result['browser_observer_preload_used'] is False
    assert [row['case'] for row in result['samples']] == result['fixed_sequence']
    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=checkout)
    print(json.dumps({'run_id': run['id'], 'original_tests_executed': True,
                      'outcomes': {row['case']: row['passed'] for row in result['samples']}}), flush=True)


if __name__ == '__main__':
    main()

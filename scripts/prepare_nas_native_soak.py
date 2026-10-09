"""Prepare immutable Soak inputs on NAS after production builds finish."""

import hashlib
import json
import tarfile
from datetime import datetime, timezone

from nas_followup_support import production_jobs
from nas_master_build_slot import wait_for_nas_build_slot
from nas_measurement_guard import begin, finish
from nas_ssh import ROOT, run_script, upload_file

COMMIT = '0ad540dd578033d45e4d0c25d89fbe57b32102a4'
FOLDER = ROOT / 'test-results/nas-parity/followup/nas-native-soak-preparation'
REMOTE = '/volume1/docker/leroy-nas-parity/nas-native-soak/0ad540dd5780'
INNER = '/var/lib/leroy-soak/0ad540dd5780'
SOURCE_SHA = 'f0c737a8133cd73f6b34c66be5081316a7047a1881583532874b40abaec59708'

PROGRAM = r'''
import hashlib,json,pathlib,subprocess,time,tarfile,shutil
root=pathlib.Path('/volume1/docker/leroy-nas-parity');assert (root/'.leroy-owned').is_file()
stage=pathlib.Path(REMOTE);assert stage.resolve().is_relative_to(root.resolve()) and stage.is_dir()
prefix=['docker','exec','leroy-nas-parity-docker-1']
def call(*args,timeout=120):return subprocess.check_output([*prefix,*args],text=True,timeout=timeout).strip()
for name,digest in FILES.items():
 with (stage/name).open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==digest,name
assert FILES['verification-source.tar.gz']==SOURCE_SHA
source=stage/'source'
assert not source.exists(),'Keep the first preparation; no implicit rebuild'
source.mkdir(mode=0o755)
with tarfile.open(stage/'verification-source.tar.gz') as archive:
 members=archive.getmembers();assert len(members)<15000 and sum(m.size for m in members)<256*1024**2
 for member in members:
  name=pathlib.PurePosixPath(member.name)
  assert not name.is_absolute() and '..' not in name.parts and (member.isdir() or member.isfile())
  path=source.joinpath(*name.parts);assert path.resolve().is_relative_to(source.resolve())
  if member.isdir():path.mkdir(parents=True,exist_ok=True,mode=0o755)
  else:
   path.parent.mkdir(parents=True,exist_ok=True,mode=0o755)
   with archive.extractfile(member) as original,path.open('xb') as output:shutil.copyfileobj(original,output)
   path.chmod(0o755 if member.mode&0o111 else 0o644)
profile=source/'deployments/linux/host/graphato-server.apparmor'
assert hashlib.sha256(profile.read_bytes()).hexdigest()==PROFILE_SHA
profiles=pathlib.Path('/sys/kernel/security/apparmor/profiles').read_text().splitlines()
assert not any(line.startswith('graphato-server ') for line in profiles),'Do not replace an existing host profile'
call('mkdir','-p',INNER,timeout=30)
for name in ['source','verification-source.tar.gz','nas-passive-http.py','nas-soak-case.py']:
 subprocess.run(['docker','cp',str(stage/name),'leroy-nas-parity-docker-1:'+INNER+'/'+name],check=True,capture_output=True,timeout=120)
# The NAS system parser cannot read ABI 4. Install its matching compiler and
# includes only in our existing Alpine test daemon, without host package changes
# or init scripts. Package signatures remain checked by apk.
call('apk','add','--no-cache','apparmor','apparmor-profiles-api','apparmor-profiles-abstractions','apparmor-profiles-tunables',timeout=180)
parser_version=call('apparmor_parser','--version',timeout=15)
call('apparmor_parser','-Q','-T',INNER+'/source/deployments/linux/host/graphato-server.apparmor',timeout=30)
call('apparmor_parser','-a','-T',INNER+'/source/deployments/linux/host/graphato-server.apparmor',timeout=30)
after_profiles=pathlib.Path('/sys/kernel/security/apparmor/profiles').read_text().splitlines()
assert set(after_profiles)==set(profiles)|{'graphato-server (enforce)'}
(stage/'apparmor-added.json').write_text(json.dumps({'profile_sha256':PROFILE_SHA,'existing_profiles_unchanged':True,
 'profile_added':'graphato-server','loader_location':'owned test daemon','loader_version':parser_version,'nas_system_packages_modified':False})+'\n')
with (stage/'native-runtime.docker.tar').open('rb') as stream:
 subprocess.run([*prefix,'docker','load'],stdin=stream,check=True,capture_output=True,timeout=900)
image=json.loads(call('docker','image','inspect',RUNTIME_REFERENCE,timeout=60))[0]
assert image['RootFS']['Layers']==RUNTIME_LAYERS
runtime=image['Id'];assert image['Config']['Labels']['org.opencontainers.image.revision']==COMMIT
probe="import hashlib,json,pathlib\np=pathlib.Path('/usr/local/bin/graphato-server')\nwith p.open('rb') as s:h=hashlib.file_digest(s,'sha256').hexdigest()\nprint(json.dumps({'server_sha256':h}))\n"
observed=json.loads(call('docker','run','--rm','--network','none','--read-only','--memory','128m','--memory-swap','128m','--entrypoint','python3',runtime,'-B','-c',probe,timeout=90))
assert observed['server_sha256']=='faab058b0006184428efe434cfaef40028b07b495d9c61b82cf719b9bcb27519'
builder='leroy-soak-prepare-'+COMMIT[:12]
assert subprocess.run([*prefix,'docker','buildx','inspect',builder],capture_output=True,timeout=30).returncode!=0
call('docker','buildx','create','--name',builder,'--driver','docker-container','--driver-opt',
 'image=moby/buildkit:v0.28.1,memory=2g,memory-swap=2g,cpu-period=100000,cpu-quota=200000','--bootstrap',timeout=240)
worker_tag='leroy-soak/browser:'+COMMIT
log=stage/'worker-build.log'
try:
 with log.open('xb') as output:
  result=subprocess.run([*prefix,'docker','buildx','build','--builder',builder,'--load','--platform','linux/amd64',
   '--progress','plain','-t',worker_tag,'-f',INNER+'/source/deployments/linux/web-tests.Dockerfile',INNER+'/source'],
   stdout=output,stderr=subprocess.STDOUT,timeout=1800)
 assert result.returncode==0,'Retain the original Dockerfile build failure'
finally:call('docker','buildx','stop',builder,timeout=90)
worker=call('docker','image','inspect',worker_tag,'--format','{{.Id}}',timeout=60)
node="const fs=require('node:fs'),c=require('node:crypto');const paths="+json.dumps(sorted(WORKER_FILES))+",files={};for(const p of paths)files[p]=c.createHash('sha256').update(fs.readFileSync('/build/'+p)).digest('hex');console.log(JSON.stringify({files,node_version:process.version,playwright_version:require('node:module').createRequire('/build/apps/desktop/package.json')('@playwright/test/package.json').version}));"
worker_proof=json.loads(call('docker','run','--rm','--network','none','--read-only','--memory','128m','--entrypoint','node',worker,'-e',node,timeout=90))
assert worker_proof['files']==WORKER_FILES and worker_proof['node_version']=='v24.14.1' and worker_proof['playwright_version']=='1.63.0'
inputs={'commit':COMMIT,'source_sha256':SOURCE_SHA,'runtime_image_id':runtime,'worker_image_id':worker,
 'helper_sha256':hashlib.sha256((source/'deployments/linux/host/postdeploy.py').read_bytes()).hexdigest(),
 'observer_sha256':FILES['nas-passive-http.py'],'coordinator_sha256':FILES['nas-soak-case.py'],
 'original_registry_digest':REGISTRY_DIGEST,'runtime_rootfs_layers_verified':True,'worker_original_files_verified':len(WORKER_FILES),
 'nas_execution':True,'test_source_modified':False,'prebuilt_worker_build_log_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),
 'preparation_builder_memory_bytes':2*1024**3,'original_test_fixture_limits_modified':False,
 'apparmor_profile_sha256':PROFILE_SHA,'apparmor_compiler_version':parser_version,'nas_system_packages_modified':False}
(stage/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
subprocess.run(['docker','cp',str(stage/'inputs.json'),'leroy-nas-parity-docker-1:'+INNER+'/inputs.json'],check=True,capture_output=True,timeout=30)
(stage/'worker-proof.json').write_text(json.dumps(worker_proof,indent=2)+'\n')
print(json.dumps(inputs),flush=True)
'''


def main():
    FOLDER.mkdir(parents=True, exist_ok=True)
    assert not (FOLDER / 'prepared-inputs.json').exists(), 'Retain the completed preparation'
    original = json.loads((ROOT / 'test-results/nas-parity/followup/native-browser-observations/web-18/runtime-docker-archive.json').read_text())
    previous_worker = json.loads((ROOT / 'test-results/nas-parity/followup/candidates/graphato' / COMMIT /
                                 'controlled-groups/web-soak-cpu-eight-round-2/jenkins-worker-content-proof.json').read_text())
    sources = {
        'verification-source.tar.gz': ROOT / '.local/nas-native-soak/verification-original-source.tar.gz',
        'native-runtime.docker.tar': ROOT / original['archive'],
        'nas-passive-http.py': ROOT / 'scripts/diagnostics/nas-passive-http.py',
        'nas-soak-case.py': ROOT / 'scripts/diagnostics/nas-soak-case.py',
    }
    hashes = {}
    for name, path in sources.items():
        with path.open('rb') as stream:
            hashes[name] = hashlib.file_digest(stream, 'sha256').hexdigest()
    assert hashes['verification-source.tar.gz'] == SOURCE_SHA
    assert hashes['native-runtime.docker.tar'] == original['archive_sha256']
    with tarfile.open(sources['verification-source.tar.gz']) as archive:
        profile_sha = hashlib.sha256(archive.extractfile('deployments/linux/host/graphato-server.apparmor').read()).hexdigest()
    # Transfer is preparation, not a performance sample. The established NAS
    # admission helper permits already observed remote postdeployment checks,
    # but rejects native compilers and low available memory. Materialization and
    # every actual comparison sample still wait for all production jobs.
    admission = wait_for_nas_build_slot(COMMIT)
    assert admission['commit'] == COMMIT
    (FOLDER / 'transfer-admission.json').write_text(json.dumps(admission, indent=2) + '\n')
    first = 'production-measurement-before-native-soak-prepare-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json'
    (FOLDER / first).write_text(json.dumps({'at': datetime.now(timezone.utc).isoformat(), **production_jobs()}, indent=2) + '\n')
    for name, path in sources.items():
        with path.open('rb') as stream:
            assert hashlib.file_digest(stream, 'sha256').hexdigest() == hashes[name], 'Preparation inputs changed while waiting'
    init = 'import pathlib\np=pathlib.Path(' + repr(REMOTE) + ')\n'
    init += "assert pathlib.Path('/volume1/docker/leroy-nas-parity/.leroy-owned').is_file()\n"
    init += "assert not p.exists(),'Retain a partial preparation; inspect it before repair'\np.mkdir(parents=True,mode=0o700)\n"
    response = run_script("python3 - <<'PY'\n" + init + "\nPY\n", ROOT / '.local/nas-ssh.json', timeout=45)
    assert response.returncode == 0, response.stderr[-1200:]
    for name, path in sources.items():
        print(json.dumps({'uploading_owned_input': name, 'bytes': path.stat().st_size}), flush=True)
        upload_file(path, REMOTE + '/' + name, ROOT / '.local/nas-ssh.json', timeout=1800)
    finish(FOLDER, 'native-soak-prepare', first)
    before = begin(FOLDER, 'native-soak-materialize')
    parameters = {'REMOTE': REMOTE, 'INNER': INNER, 'COMMIT': COMMIT, 'SOURCE_SHA': SOURCE_SHA,
                  'FILES': hashes, 'RUNTIME_REFERENCE': original['test_reference'], 'RUNTIME_LAYERS': original['rootfs_diff_ids'],
                  'REGISTRY_DIGEST': original['original_registry_manifest_digest'], 'WORKER_FILES': previous_worker['files'],
                  'PROFILE_SHA': profile_sha}
    program = '\n'.join(key + '=' + repr(value) for key, value in parameters.items()) + '\n' + PROGRAM
    compile(program, 'NAS immutable Soak preparation', 'exec')
    (FOLDER / 'preparation-program.py').write_text(program)
    response = run_script("python3 - <<'PY'\n" + program + "\nPY\n", ROOT / '.local/nas-ssh.json', sudo=True, timeout=3000)
    finish(FOLDER, 'native-soak-materialize', before)
    if response.returncode:
        private = ROOT / '.local/nas-native-soak/preparation-failure.log'
        private.parent.mkdir(parents=True, exist_ok=True)
        private.write_text(response.stderr, encoding='utf-8')
        (FOLDER / 'preparation-failure.json').write_text(json.dumps({
            'exit_code': response.returncode, 'stdout_sha256': hashlib.sha256(response.stdout.encode()).hexdigest(),
            'stderr_sha256': hashlib.sha256(response.stderr.encode()).hexdigest(),
            'tests_started': False, 'source_or_tests_modified': False,
        }, indent=2) + '\n')
        raise RuntimeError('NAS Soak preparation failed; inspect and preserve this attempt')
    value = json.loads(response.stdout)
    (FOLDER / 'prepared-inputs.json').write_text(json.dumps(value, indent=2) + '\n')
    print(json.dumps({'nas_soak_inputs_prepared': True, 'inputs': value}), flush=True)


if __name__ == '__main__':
    main()

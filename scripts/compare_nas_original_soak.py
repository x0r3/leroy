"""Fixed Jenkins/Leroy/Leroy/Jenkins samples of the original Soak command on NAS.

This dispatch diagnostic retains failed samples. It is not complete release-gate
acceptance and does not change tests, application sources or limiter settings.
"""

import argparse
import base64
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import tarfile
import time
import xml.etree.ElementTree as ET
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
from urllib.parse import urlencode

from compare_nas_antares import client
from compare_nas_job import collect_artifacts
from nas_followup_support import inner, jenkins_api, production_jobs, start_jenkins
from nas_gitea_target import idle
from nas_measurement_guard import begin, finish
from nas_soak_metadata import qualify
from nas_ssh import ROOT, run_script, upload_file
from prepare_nas_native_soak import FOLDER as PREPARATION
from prepare_nas_native_soak import INNER, REMOTE

from leroy.schema import Pipeline, Step

FOLDER = ROOT / 'test-results/nas-parity/followup/nas-original-soak-engine-comparison'
JOB = 'leroy-original-soak-nas'
ORDER = ('jenkins-1', 'leroy-1', 'leroy-2', 'jenkins-2')
SERIES = ''

HOST_OBSERVATION = r'''
import json,pathlib,time
assert pathlib.Path('/volume1/docker/leroy-nas-parity/.leroy-owned').is_file()
mem={}
for line in pathlib.Path('/proc/meminfo').read_text().splitlines():
 key,value=line.split(':',1)
 if key in ('MemTotal','MemAvailable','SwapTotal','SwapFree'):mem[key]=int(value.split()[0])*1024
pressure={p:pathlib.Path('/proc/pressure/'+p).read_text().strip() for p in ('cpu','memory','io')}
print(json.dumps({'at_epoch':time.time(),'memory_bytes':mem,'pressure':pressure,
 'load_average':pathlib.Path('/proc/loadavg').read_text().split()[:3],
 'cpu_ticks':pathlib.Path('/proc/stat').read_text().splitlines()[0]}))
'''


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def host_observation(folder):
    response = run_script("python3 - <<'PY'\n" + HOST_OBSERVATION + "\nPY\n", ROOT / '.local/nas-ssh.json', timeout=30)
    assert response.returncode == 0, response.stderr[-1000:]
    value = json.loads(response.stdout)
    try:
        value['production'] = production_jobs()
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        # A bounded read failure is missing evidence, not a test result or idle
        # production. Keep observing the existing build; the final guard must
        # independently qualify the entire before/after build-history window.
        value['production'] = {'read_only': True, 'observation_error': type(error).__name__,
                               'active_builds': None, 'older_concurrent_build_history_verified': False}
    with (folder / 'load-observations.jsonl').open('a', encoding='utf-8') as output:
        output.write(json.dumps(value) + '\n')


def jenkins_definition(launcher, inputs):
    def groovy(value):
        return "'" + value.replace('\\', '\\\\').replace("'", "\\'").replace('\r', '\\r').replace('\n', '\\n') + "'"

    script = '''pipeline {
  agent any
  options { disableConcurrentBuilds(); timestamps(); timeout(time: 65, unit: 'MINUTES') }
  parameters { choice(name: 'SAMPLE_ID', choices: ['jenkins-1', 'jenkins-2'], description: 'Fixed original samples, without retries') }
  stages {
    stage('Original Soak') {
      steps {
        deleteDir()
        writeFile file: 'nas-soak-launcher.py', text: LAUNCHER
        withEnv(['SOAK_CASE=' + params.SAMPLE_ID]) {
          sh 'python3 nas-soak-launcher.py --case "$SOAK_CASE" --runtime RUNTIME --coordinator-sha256 COORDINATOR SERIES_ARGUMENT'
        }
      }
    }
  }
  post { always { archiveArtifacts artifacts: 'diagnostic/**', allowEmptyArchive: true } }
}
'''.replace('LAUNCHER', groovy(launcher)).replace('RUNTIME', inputs['runtime_image_id']).replace('COORDINATOR', inputs['coordinator_sha256']).replace('SERIES_ARGUMENT', '--series ' + SERIES if SERIES else '')
    root = ET.Element('flow-definition', {'plugin': 'workflow-job'})
    ET.SubElement(root, 'description').text = 'Owned Leroy NAS parity: fixed original Soak dispatch diagnostic. No production targets.'
    ET.SubElement(root, 'keepDependencies').text = 'false'
    properties = ET.SubElement(root, 'properties')
    parameters = ET.SubElement(ET.SubElement(properties, 'hudson.model.ParametersDefinitionProperty'), 'parameterDefinitions')
    choice = ET.SubElement(parameters, 'hudson.model.ChoiceParameterDefinition')
    ET.SubElement(choice, 'name').text = 'SAMPLE_ID'
    choices = ET.SubElement(ET.SubElement(choice, 'choices', {'class': 'java.util.Arrays$ArrayList'}), 'a', {'class': 'string-array'})
    for value in ('jenkins-1', 'jenkins-2'):
        ET.SubElement(choices, 'string').text = value
    definition = ET.SubElement(root, 'definition', {'class': 'org.jenkinsci.plugins.workflow.cps.CpsFlowDefinition', 'plugin': 'workflow-cps'})
    ET.SubElement(definition, 'script').text = script
    ET.SubElement(definition, 'sandbox').text = 'true'
    ET.SubElement(root, 'triggers')
    ET.SubElement(root, 'disabled').text = 'false'
    return ET.tostring(root, encoding='unicode')


def collect_jenkins(number, folder):
    # Read only our explicitly named test job and its bounded public artifacts.
    program = 'JOB=' + repr(JOB) + '\nNUMBER=' + repr(number) + '\n' + r'''
import base64,hashlib,json,pathlib,xml.etree.ElementTree as ET
assert pathlib.Path('/volume1/docker/leroy-nas-parity/.leroy-owned').is_file()
root=pathlib.Path('/volume1/@docker/volumes/leroy-nas-parity_engine/_data/volumes/jenkins-parity-aligned-home/_data').resolve(strict=True)
build=root/'jobs'/JOB/'builds'/str(NUMBER);assert build.resolve().is_relative_to(root) and build.is_dir()
tree=ET.parse(build/'build.xml').getroot();assert tree.findtext('completed')=='true'
state={'number':NUMBER,'result':tree.findtext('result'),'building':False,'duration':tree.findtext('duration'),
       'timestamp':tree.findtext('timestamp'),'scm_checkout_performed':False}
archive=build/'archive/diagnostic';assert archive.resolve().is_relative_to(build.resolve())
items=[];total=0
for name in ('result.json','launcher-result.json','coordinator-console.log','artifacts.tar.gz'):
 p=archive/name
 if not p.is_file():continue
 assert not p.is_symlink() and p.resolve().is_relative_to(archive.resolve())
 size=p.stat().st_size;total+=size;assert size<128*1024**2 and total<160*1024**2
 with p.open('rb') as s:digest=hashlib.file_digest(s,'sha256').hexdigest()
 items.append({'name':name,'sha256':digest,'size':size,'content':base64.b64encode(p.read_bytes()).decode()})
print(json.dumps({'build':state,'artifacts':items}))
'''
    response = run_script("python3 - <<'PY'\n" + program + "\nPY\n", ROOT / '.local/nas-ssh.json', sudo=True, timeout=150)
    assert response.returncode == 0, response.stderr[-1000:]
    value = json.loads(response.stdout)
    destination = folder / 'diagnostic'
    destination.mkdir(exist_ok=True)
    for item in value['artifacts']:
        content = base64.b64decode(item.pop('content'), validate=True)
        assert len(content) == item['size'] and hashlib.sha256(content).hexdigest() == item['sha256']
        (destination / item['name']).write_bytes(content)
    save(folder / 'jenkins-receipt.json', value)
    return value['build']


def run_jenkins(case, folder):
    before = begin(folder, case)
    idle()
    status = json.loads(jenkins_api('/job/' + JOB + '/api/json?tree=nextBuildNumber,lastBuild[building]')['text'])
    assert not status.get('lastBuild') or not status['lastBuild']['building']
    number = status['nextBuildNumber']
    save(folder / 'dispatch-intent.json', {'engine': 'jenkins', 'case': case, 'build_number': number, 'production_guard_before': before})
    submitted = jenkins_api('/job/' + JOB + '/buildWithParameters', urlencode({'SAMPLE_ID': case}), 'application/x-www-form-urlencoded')
    save(folder / 'dispatch.json', {'queue_location': submitted['headers'].get('Location'), 'build_number': number})
    deadline = time.monotonic() + 4200
    observed_at = 0
    while time.monotonic() < deadline:
        if time.monotonic() >= observed_at:
            host_observation(folder)
            observed_at = time.monotonic() + 45
        current = json.loads(jenkins_api('/job/' + JOB + '/api/json?tree=lastBuild[number,result,building]')['text']).get('lastBuild')
        if current and current['number'] == number and not current['building'] and current['result']:
            break
        time.sleep(10)
    else:
        raise TimeoutError('Owned Jenkins sample is still active; do not start another sample')
    result = collect_jenkins(number, folder)
    host_observation(folder)
    qualification = finish(folder, case, before)
    return folder / 'diagnostic', result, qualification


def run_leroy(case, folder, launcher, inputs):
    before = begin(folder, case)
    idle()
    program = 'import pathlib,subprocess,sys\np=pathlib.Path("nas-soak-launcher.py")\np.write_bytes(' + repr(launcher.encode()) + ')\n'
    command = ['python3', 'nas-soak-launcher.py', '--case', case, '--runtime', inputs['runtime_image_id'],
               '--coordinator-sha256', inputs['coordinator_sha256']]
    if SERIES:
        command += ['--series', SERIES]
    program += 'raise SystemExit(subprocess.run(' + repr(command) + ').returncode)\n'
    spec = Pipeline(id='leroy-nas-diagnostics', name='NAS: Original Soak ' + case, group='Abnahme', enabled=False,
                    profile='graphato', timeout=4200,
                    source={'kind': 'diagnostic', 'scenario': case, 'commit': inputs['commit'], 'source_sha256': inputs['source_sha256']},
                    steps=[Step(id='soak', name='Original Soak', command=['python', '-c', program], timeout=4000,
                                artifacts=['diagnostic/**'])])
    save(folder / 'definition.json', spec.model_dump())
    with closing(client()) as api:
        ps = api.get('/api/pipelines')
        ps.raise_for_status()
        assert not any(p['enabled'] for p in ps.json())
        previous = next(p['spec'] for p in ps.json() if p['id'] == spec.id)
        assert previous['source'].get('kind') == 'diagnostic'
        private = ROOT / '.local/nas-native-soak' / ((SERIES + '-' if SERIES else '') + case + '-previous-leroy-definition.json')
        private.parent.mkdir(parents=True, exist_ok=True)
        assert not private.exists(), 'Retain an earlier sample definition'
        save(private, previous)
        api.put('/api/pipelines/' + spec.id, json=spec.model_dump()).raise_for_status()
        dispatched = False
        try:
            response = api.post('/api/pipelines/' + spec.id + '/runs', json={'commit': inputs['commit']})
            response.raise_for_status()
            run_id = response.json()['id']
            dispatched = True
            save(folder / 'dispatch.json', {'engine': 'leroy', 'case': case, 'run_id': run_id, 'production_guard_before': before})
            deadline, observed_at = time.monotonic() + 4400, 0
            while time.monotonic() < deadline:
                if time.monotonic() >= observed_at:
                    host_observation(folder)
                    observed_at = time.monotonic() + 45
                response = api.get('/api/runs/' + run_id)
                response.raise_for_status()
                run = response.json()
                if run['status'] not in ('queued', 'running', 'waiting'):
                    break
                time.sleep(10)
            else:
                raise TimeoutError('Leroy sample is still active; retain its definition and halt')
            dispatched = False
            save(folder / 'leroy-run.json', run)
            collect_artifacts(api, run, folder)
            destination = folder / 'leroy-artifacts/soak/diagnostic'
            host_observation(folder)
            qualification = finish(folder, case, before)
            return destination, run, qualification
        finally:
            if not dispatched:
                current = api.get('/api/pipelines')
                current.raise_for_status()
                definition = next(p['spec'] for p in current.json() if p['id'] == spec.id)
                assert Pipeline.model_validate(definition) == spec, 'Do not overwrite someone else\'s diagnostic change'
                api.put('/api/pipelines/' + spec.id, json=previous).raise_for_status()
                save(folder / 'definition-restored.json', {'restored': True, 'previous_sha256': hashlib.sha256(private.read_bytes()).hexdigest()})


def analyze_case(artifacts, folder, case):
    result = json.loads((artifacts / 'result.json').read_text())
    launch = json.loads((artifacts / 'launcher-result.json').read_text())
    assert result['case'] == case and launch['case'] == case
    archive = artifacts / 'artifacts.tar.gz'
    with archive.open('rb') as stream:
        assert hashlib.file_digest(stream, 'sha256').hexdigest() == result['artifact_archive_sha256']
    destination = folder / 'original-artifacts'
    destination.mkdir(exist_ok=False)
    count, size = 0, 0
    with tarfile.open(archive) as tar:
        for member in tar:
            name = pathlib.PurePosixPath(member.name)
            count += 1
            size += member.size
            assert member.isfile() and not name.is_absolute() and '..' not in name.parts and count < 2000 and size < 320*1024**2
            path = destination.joinpath(*name.parts)
            assert path.resolve().is_relative_to(destination.resolve())
            path.parent.mkdir(parents=True, exist_ok=True)
            with tar.extractfile(member) as source, path.open('xb') as output:
                shutil.copyfileobj(source, output)
    metadata = destination / 'http-metadata.jsonl'
    requests, responses = [], []
    if metadata.is_file():
        for line in metadata.read_text().splitlines():
            row = json.loads(line)
            if row['kind'] == 'request':
                requests.append(row)
            elif row['kind'] == 'response':
                responses.append(row)
    rate_limited = [r for r in responses if r['status'] == 429]
    first = min(rate_limited, key=lambda r: r['response_headers_ns']) if rate_limited else None
    provider = [r for r in requests if r.get('command') == 'listProviderInstallations']
    qualification = qualify([*requests, *responses], result['observation'])
    starts = sorted(r['headers_received_ns'] for r in requests if r['route'] in ('/api/v1/commands', '/api/v1/events'))
    peaks = {}
    for seconds in (1, 5):
        left, maximum = 0, 0
        for right, stamp in enumerate(starts):
            while stamp - starts[left] > seconds * 10**9:
                left += 1
            maximum = max(maximum, right - left + 1)
        peaks[str(seconds) + '_seconds'] = maximum
    value = {'case': case, 'original_soak_executed': result['original_case_executed'],
             'passed': bool(result['case_result'] and result['case_result']['passed']),
             'cleanup_complete': result['cleanup_complete'], 'oom_killed': launch['oom_killed'],
             'runtime_image_id': result['inputs']['runtime_image_id'], 'worker_image_id': result['inputs']['worker_image_id'],
             'requests_observed_at_server_interface': len(requests), 'provider_reads': len(provider),
             'http_429_responses': sum(r['status'] == 429 for r in responses), 'first_429_metadata': first,
             'command_counts': dict(Counter(r['command'] for r in requests if r.get('command'))),
             'commands_and_events_peak_requests_per_window': peaks,
             **qualification,
             'observation': result['observation'], 'actual_rate_limiter_admission_times_observed': False,
             'unchanged_tests_application_and_limits': not result['tests_and_application_modified'] and not result['rate_limits_modified'],
             'complete_original_pipeline_acceptance': False, 'observer_overhead_excluded': False}
    save(folder / 'analysis.json', value)
    assert value['original_soak_executed'] and value['cleanup_complete'] and not value['oom_killed'], 'Do not continue after a precondition/cleanup failure'
    return value


def remove_temporary_profile():
    program = 'STAGE=' + repr(REMOTE) + '\nINNER=' + repr(INNER) + '\n' + r'''
import hashlib,json,pathlib,subprocess
stage=pathlib.Path(STAGE)
assert pathlib.Path('/volume1/docker/leroy-nas-parity/.leroy-owned').is_file()
owned=json.loads((stage/'apparmor-added.json').read_text());assert owned['profile_added']=='graphato-server'
profile=stage/'source/deployments/linux/host/graphato-server.apparmor'
assert hashlib.sha256(profile.read_bytes()).hexdigest()==owned['profile_sha256']
users=[]
for entry in pathlib.Path('/proc').iterdir():
 if not entry.name.isdecimal():continue
 try:current=(entry/'attr/current').read_text()
 except (FileNotFoundError,ProcessLookupError):continue
 if current.startswith('graphato-server'):users.append(int(entry.name))
assert not users,'Keep a profile used by a live process; do not change that process'
before=set(pathlib.Path('/sys/kernel/security/apparmor/profiles').read_text().splitlines())
assert 'graphato-server (enforce)' in before
subprocess.run(['docker','exec','leroy-nas-parity-docker-1','apparmor_parser','-R','-T',
 INNER+'/source/deployments/linux/host/graphato-server.apparmor'],check=True,capture_output=True,timeout=30)
after=set(pathlib.Path('/sys/kernel/security/apparmor/profiles').read_text().splitlines())
assert after==before-{'graphato-server (enforce)'}
print(json.dumps({'temporary_profile_removed':True,'other_loaded_profiles_unchanged':True,'nas_system_packages_modified':False}))
'''
    response = run_script("python3 - <<'PY'\n" + program + "\nPY\n", ROOT / '.local/nas-ssh.json', sudo=True, timeout=60)
    assert response.returncode == 0, 'Keep and inspect a profile cleanup failure without changing other processes'
    save(FOLDER / 'temporary-profile-removed.json', json.loads(response.stdout))


def prepare_series(inputs):
    """Retain previous attempts while sharing the same immutable application inputs."""
    updated = dict(inputs, diagnostic_series=SERIES)
    coordinator = (ROOT / 'scripts/diagnostics/nas-soak-case.py').read_bytes()
    observer = (ROOT / 'scripts/diagnostics/nas-passive-http.py').read_bytes()
    updated['coordinator_sha256'] = hashlib.sha256(coordinator).hexdigest()
    updated['previous_observer_sha256'] = inputs['observer_sha256']
    updated['observer_sha256'] = hashlib.sha256(observer).hexdigest()
    updated['observer_script_path'] = INNER + '/series/' + SERIES + '/nas-passive-http.py'
    transfer = REMOTE + '/series-upload/' + SERIES
    create = "import pathlib;assert pathlib.Path('/volume1/docker/leroy-nas-parity/.leroy-owned').is_file();pathlib.Path(" + repr(transfer) + ").mkdir(parents=True,mode=0o700)"
    created = run_script("python3 - <<'PY'\n" + create + "\nPY\n", ROOT / '.local/nas-ssh.json', timeout=30)
    assert created.returncode == 0, created.stderr[-1000:]
    for name, data in [('nas-soak-case.py', coordinator), ('nas-passive-http.py', observer)]:
        path = FOLDER / name
        path.write_bytes(data)
        upload_file(path, transfer + '/' + name, ROOT / '.local/nas-ssh.json', timeout=60)
    program = 'INNER=' + repr(INNER) + '\nREMOTE=' + repr(REMOTE) + '\nSERIES=' + repr(SERIES) + '\n'
    program += 'INPUTS=' + repr(updated) + '\nTRANSFER=' + repr(transfer) + '\n' + r'''
import hashlib,json,pathlib,subprocess
assert pathlib.Path('/volume1/docker/leroy-nas-parity/.leroy-owned').is_file()
stage=pathlib.Path(REMOTE);old=json.loads((stage/'inputs.json').read_text())
transfer=pathlib.Path(TRANSFER);assert transfer.resolve().is_relative_to(stage.resolve())
COORDINATOR=(transfer/'nas-soak-case.py').read_bytes();OBSERVER=(transfer/'nas-passive-http.py').read_bytes()
for key in ('commit','source_sha256','runtime_image_id','worker_image_id','helper_sha256','apparmor_profile_sha256'):
 assert old[key]==INPUTS[key],key
assert old['observer_sha256']==INPUTS['previous_observer_sha256']
assert hashlib.sha256(COORDINATOR).hexdigest()==INPUTS['coordinator_sha256']
assert hashlib.sha256(OBSERVER).hexdigest()==INPUTS['observer_sha256']
target=stage/'series'/SERIES;assert target.resolve().is_relative_to(stage.resolve()) and not target.exists()
target.mkdir(parents=True,mode=0o700)
(target/'nas-soak-case.py').write_bytes(COORDINATOR)
(target/'nas-passive-http.py').write_bytes(OBSERVER)
(target/'inputs.json').write_text(json.dumps(INPUTS,indent=2)+'\n')
prefix=['docker','exec','leroy-nas-parity-docker-1']
inner=INNER+'/series/'+SERIES
subprocess.run([*prefix,'test','!','-e',inner],check=True,capture_output=True,timeout=30)
subprocess.run([*prefix,'mkdir','-p',INNER+'/series'],check=True,capture_output=True,timeout=30)
subprocess.run(['docker','cp',str(target),'leroy-nas-parity-docker-1:'+inner],check=True,capture_output=True,timeout=60)
profile=stage/'source/deployments/linux/host/graphato-server.apparmor'
owned=json.loads((stage/'apparmor-added.json').read_text())
assert owned['profile_added']=='graphato-server' and owned['profile_sha256']==INPUTS['apparmor_profile_sha256']
assert hashlib.sha256(profile.read_bytes()).hexdigest()==INPUTS['apparmor_profile_sha256']
before=set(pathlib.Path('/sys/kernel/security/apparmor/profiles').read_text().splitlines())
assert not any(p.startswith('graphato-server ') for p in before),'Do not replace an existing profile'
subprocess.run([*prefix,'apparmor_parser','-a','-T',INNER+'/source/deployments/linux/host/graphato-server.apparmor'],check=True,capture_output=True,timeout=30)
assert set(pathlib.Path('/sys/kernel/security/apparmor/profiles').read_text().splitlines())==before|{'graphato-server (enforce)'}
print(json.dumps({'diagnostic_series':SERIES,'previous_series_preserved':True,'application_inputs_unchanged':True,'original_profile_reloaded':True,'other_profiles_unchanged':True}))
'''
    (FOLDER / 'series-preparation-program.py').write_text(program, encoding='utf-8')
    response = run_script("python3 - <<'PY'\n" + program + "\nPY\n", ROOT / '.local/nas-ssh.json', sudo=True, timeout=120)
    assert response.returncode == 0, response.stderr[-1500:]
    save(FOLDER / 'series-preparation.json', json.loads(response.stdout))
    save(FOLDER / 'prepared-inputs.json', updated)
    return updated


def check_observation_prerequisites(inputs):
    """Validate namespace entry and the kernel filter before any original test."""
    image = inputs['runtime_image_id']
    observer_script = inputs.get('observer_script_path', INNER + '/nas-passive-http.py')
    name = 'leroy-soak-network-probe-0ad540dd5780'
    probe = inner('run', '-d', '--name', name, '--label', 'io.leroy.nas-soak=network-probe',
                  '--network', 'none', '--read-only', '--user', '1000:1000', '--cap-drop', 'ALL',
                  '--security-opt', 'apparmor=graphato-server', '--memory', '64m', '--memory-swap', '64m',
                  '--cpus', '0.1', '--entrypoint', 'python3', image, '-B', '-c', 'import time;time.sleep(120)').strip()
    state = json.loads(inner('inspect', probe))[0]
    assert state['Image'] == image and state['State']['Running']
    program = 'import importlib.util,socket,pathlib,json\n'
    program += 's=importlib.util.spec_from_file_location("observer",' + repr(observer_script) + ')\n'
    program += 'm=importlib.util.module_from_spec(s);s.loader.exec_module(m)\n'
    program += 'm.join_fixture_network(' + str(state['State']['Pid']) + ')\n'
    program += 'p=socket.socket(socket.AF_PACKET,socket.SOCK_RAW,socket.htons(0x0003));m.filter_http(p);p.close()\n'
    program += 'status=pathlib.Path("/proc/self/status").read_text();cap=int(next(l.split()[1] for l in status.splitlines() if l.startswith("CapEff:")),16)\n'
    program += 'assert cap==1<<13;print(json.dumps({"namespace_entry_validated":True,"kernel_filter_validated":True,"only_net_raw_retained":True,"original_tests_started":False}))\n'
    try:
        raw = inner('run', '--rm', '--network', 'none', '--pid', 'host', '--read-only', '--user', '0:0',
                    '--cap-drop', 'ALL', '--cap-add', 'NET_RAW', '--cap-add', 'SYS_ADMIN', '--cap-add', 'SYS_PTRACE',
                    '--cap-add', 'DAC_OVERRIDE', '--security-opt', 'apparmor=graphato-server',
                    '--security-opt', 'no-new-privileges:true', '--memory', '64m', '--memory-swap', '64m', '--cpus', '0.1',
                    '--mount', 'type=bind,src=' + INNER + ',dst=' + INNER + ',readonly',
                    '--entrypoint', 'python3', image, '-B', '-c', program)
        save(FOLDER / 'observation-prerequisites.json', json.loads(raw))
        directory = INNER + '/series/' + SERIES + '/observer-preflight' if SERIES else INNER + '/observer-preflight'
        inner('run', '--rm', '--network', 'none', '--read-only', '--memory', '128m', '--user', '0:0',
              '--mount', 'type=bind,src=' + INNER + ',dst=' + INNER,
              '--entrypoint', 'python3', image, '-B', '-c', 'import pathlib;pathlib.Path(' + repr(directory) + ').mkdir(mode=0o700)')
        observer = inner('run', '-d', '--name', 'leroy-soak-observer-probe-' + (SERIES or 'original'),
                         '--label', 'io.leroy.nas-soak=observer-preflight', '--network', 'none', '--pid', 'host',
                         '--read-only', '--user', '0:0', '--cap-drop', 'ALL', '--cap-add', 'NET_RAW',
                         '--cap-add', 'SYS_ADMIN', '--cap-add', 'SYS_PTRACE', '--cap-add', 'DAC_OVERRIDE',
                         '--security-opt', 'apparmor=graphato-server', '--security-opt', 'no-new-privileges:true',
                         '--memory', '64m', '--memory-swap', '64m', '--cpus', '0.1', '--pids-limit', '32',
                         '--mount', 'type=bind,src=' + observer_script + ',dst=/observe.py,readonly',
                         '--mount', 'type=bind,src=' + directory + ',dst=/metadata',
                         '--entrypoint', 'python3', image, '-B', '/observe.py', '--output', '/metadata/http-metadata.jsonl',
                         '--network-namespace-pid', str(state['State']['Pid'])).strip()
        try:
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                captured = inner('logs', '--tail', '60', observer)
                (FOLDER / 'observer-prerequisite-console.log').write_text(captured, encoding='utf-8')
                current = json.loads(inner('inspect', observer))[0]
                assert current['State']['Running'], 'Retain observer startup failure before running any original test'
                if 'Passive metadata observer ready' in captured:
                    break
                time.sleep(1)
            else:
                raise TimeoutError('Observer did not become ready')
            inner('stop', '--time', '5', observer)
            assert json.loads(inner('inspect', observer))[0]['State']['ExitCode'] == 0
            readback = 'import pathlib,json;rows=[json.loads(l) for l in pathlib.Path(' + repr(directory + '/http-metadata.jsonl') + ').read_text().splitlines()];assert rows[0]["kind"]=="observer-start" and rows[-1]["kind"]=="observer-end";print(json.dumps({"observer_file_write_and_shutdown_validated":True,"original_tests_started":False}))'
            proof = inner('run', '--rm', '--network', 'none', '--read-only', '--memory', '128m', '--user', '0:0',
                          '--mount', 'type=bind,src=' + INNER + ',dst=' + INNER + ',readonly',
                          '--entrypoint', 'python3', image, '-B', '-c', readback)
            save(FOLDER / 'observer-output-prerequisites.json', json.loads(proof))
        finally:
            current = json.loads(inner('inspect', observer))[0]
            assert current['Config']['Labels']['io.leroy.nas-soak'] == 'observer-preflight'
            inner('rm', '-f', observer)
        # The observer creates no Docker namespace-sharing dependency. The probe
        # can be removed independently, just like the original test's server.
    finally:
        current = json.loads(inner('inspect', probe))[0]
        assert current['Config']['Labels']['io.leroy.nas-soak'] == 'network-probe'
        inner('rm', '-f', probe)


def continue_completed_prefix(previous, inputs):
    """Continue only after a retained setup failure; never retry an executed test."""
    assert SERIES and previous != SERIES and re.fullmatch('[a-z0-9][a-z0-9-]{0,31}', previous)
    folder = ROOT / 'test-results/nas-parity/followup' / ('nas-original-soak-engine-comparison-' + previous)
    assert folder.is_dir() and not folder.is_symlink() and not (folder / 'analysis.json').exists()
    progress = json.loads((folder / 'progress.json').read_text())
    samples = progress['samples']
    assert 0 < len(samples) < len(ORDER) and list(samples) == list(ORDER[:len(samples)])
    old = json.loads((folder / 'prepared-inputs.json').read_text())
    for key in ('commit', 'source_sha256', 'runtime_image_id', 'worker_image_id', 'helper_sha256',
                'observer_sha256', 'coordinator_sha256'):
        assert old[key] == inputs[key], 'Do not merge samples with changed inputs: ' + key
    next_case = ORDER[len(samples)]
    failure = json.loads((folder / next_case / 'analysis.json').read_text())
    assert not failure['original_soak_executed'] and failure['cleanup_complete'] and not failure['oom_killed']
    controllers = [json.loads((f / 'jenkins-controller-before.json').read_text()) for f in (folder, FOLDER)]
    for key in ('id', 'image', 'memory_bytes'):
        assert controllers[0][key] == controllers[1][key]
    for case, value in samples.items():
        assert value['original_soak_executed'] and value['cleanup_complete'] and not value['oom_killed']
        assert value['quiet_production_window'] and value['unchanged_tests_application_and_limits']
        expected = ('SUCCESS' if value['passed'] else 'FAILURE') if case.startswith('jenkins') else ('succeeded' if value['passed'] else 'failed')
        assert value['ci_result'] == expected
        source = folder / case
        assert not any(p.is_symlink() for p in source.rglob('*'))
        shutil.copytree(source, FOLDER / case)
        value['continued_from_evidence_folder'] = str(source.relative_to(ROOT))
    save(FOLDER / 'continuation-receipt.json', {'previous_series': previous, 'inherited_samples': list(samples),
                                              'retained_setup_failure': str((folder / next_case).relative_to(ROOT)),
                                              'executed_tests_retried': False, 'immutable_inputs_identical': True,
                                              'test_controller_restarted_between_attempts': True})
    return samples


def main():
    global SERIES, FOLDER, JOB
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--series', default='', help='Explicit new attempt; earlier complete and partial samples remain untouched')
    parser.add_argument('--continue-from', help='Retain a completed prefix and continue after an original fixture setup failure')
    args = parser.parse_args()
    SERIES = args.series
    assert not SERIES or re.fullmatch('[a-z0-9][a-z0-9-]{0,31}', SERIES)
    if SERIES:
        FOLDER = FOLDER.with_name(FOLDER.name + '-' + SERIES)
        JOB += '-' + SERIES
    inputs = json.loads((PREPARATION / 'prepared-inputs.json').read_text())
    launcher = (ROOT / 'scripts/diagnostics/nas-soak-launcher.py').read_text()
    assert not FOLDER.exists(), 'Preserve the first complete or partial fixed-order series'
    FOLDER.mkdir(parents=True)
    baseline = begin(FOLDER, 'initialize')
    idle()
    state = json.loads(inner('inspect', 'jenkins-parity'))[0]
    original_running = state['State']['Running']
    save(FOLDER / 'jenkins-controller-before.json', {'id': state['Id'], 'running': original_running,
                                                  'memory_bytes': state['HostConfig']['Memory'], 'image': state['Image']})
    results = {}
    profile_added = not SERIES
    try:
        if SERIES:
            inputs = prepare_series(inputs)
            profile_added = True
        definition = jenkins_definition(launcher, inputs)
        save(FOLDER / 'plan.json', {'created_at': datetime.now(timezone.utc).isoformat(), 'series': SERIES,
                                  'order': ORDER, 'inputs': inputs, 'launcher_sha256': hashlib.sha256(launcher.encode()).hexdigest(),
                                  'test_changes_authorized': False, 'full_pipeline_acceptance': False,
                                  'fresh_fixture_per_sample': True, 'implicit_retries': False})
        (FOLDER / 'jenkins-definition.xml').write_text(definition, encoding='utf-8')
        check_observation_prerequisites(inputs)
        if not original_running:
            start_jenkins()
        jobs = json.loads(jenkins_api('/api/json?tree=jobs[name]')['text'])['jobs']
        assert JOB not in {j['name'] for j in jobs}, 'Keep an existing diagnostic job unchanged'
        jenkins_api('/createItem?' + urlencode({'name': JOB}), definition, 'application/xml')
        finish(FOLDER, 'initialize', baseline)
        if args.continue_from:
            results = continue_completed_prefix(args.continue_from, inputs)
            save(FOLDER / 'progress.json', {'complete': False, 'samples': results})
        for case in ORDER:
            if case in results:
                continue
            folder = FOLDER / case
            folder.mkdir()
            print(json.dumps({'starting_fixed_sample': case}), flush=True)
            if case.startswith('jenkins'):
                artifacts, ci, qualification = run_jenkins(case, folder)
            else:
                artifacts, ci, qualification = run_leroy(case, folder, launcher, inputs)
            value = analyze_case(artifacts, folder, case)
            value['quiet_production_window'] = qualification['native_jenkins_quiet_window_verified']
            value['ci_result'] = ci.get('result', ci.get('status'))
            expected = ('SUCCESS' if value['passed'] else 'FAILURE') if case.startswith('jenkins') else ('succeeded' if value['passed'] else 'failed')
            assert value['ci_result'] == expected, 'CI must retain the real original test result'
            results[case] = value
            save(FOLDER / 'progress.json', {'complete': False, 'samples': results})
            print(json.dumps({'completed_sample': case, 'passed': value['passed'], 'ci_result': value['ci_result'],
                              'quiet_production_window': value['quiet_production_window']}), flush=True)
        assert len({r['runtime_image_id'] for r in results.values()}) == 1
        assert len({r['worker_image_id'] for r in results.values()}) == 1
        save(FOLDER / 'analysis.json', {'fixed_order_complete': True, 'samples': results,
                                      'quiet_production_windows_all': all(r['quiet_production_window'] for r in results.values()),
                                      'same_immutable_runtime_and_worker': True, 'unchanged_test_source_and_limits': True,
                                      'complete_original_pipeline_acceptance': False, 'production_ready': False,
                                      'historical_difference_root_cause_proven': False, 'equal_background_load_proven': False})
    finally:
        if not (FOLDER / 'production-measurement-qualification-initialize.json').exists():
            finish(FOLDER, 'initialize', baseline)
        idle()
        if not original_running:
            current = json.loads(inner('inspect', 'jenkins-parity'))[0]
            assert current['Id'] == state['Id']
            inner('stop', '--time', '45', state['Id'], timeout=75)
            save(FOLDER / 'jenkins-controller-restored.json', {'id': state['Id'], 'running': False,
                                                             'all_samples_same_controller_baseline': not bool(args.continue_from),
                                                             'controller_configuration_restored': True})
        if profile_added and not inner('ps', '-q', '--filter', 'label=io.graphato.e2e.owner').strip():
            remove_temporary_profile()


if __name__ == '__main__':
    main()

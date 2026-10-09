"""Fixed Jenkins/Leroy/Leroy/Jenkins samples of the original Soak command on NAS.

This dispatch diagnostic retains failed samples. It is not complete release-gate
acceptance and does not change tests, application sources or limiter settings.
"""

import base64
import hashlib
import json
import pathlib
import shutil
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
from nas_ssh import ROOT, run_script
from prepare_nas_native_soak import FOLDER as PREPARATION
from prepare_nas_native_soak import INNER, REMOTE

from leroy.schema import Pipeline, Step

FOLDER = ROOT / 'test-results/nas-parity/followup/nas-original-soak-engine-comparison'
JOB = 'leroy-original-soak-nas'
ORDER = ('jenkins-1', 'leroy-1', 'leroy-2', 'jenkins-2')

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
    value['production'] = production_jobs()
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
          sh 'python3 nas-soak-launcher.py --case "$SOAK_CASE" --runtime RUNTIME --coordinator-sha256 COORDINATOR'
        }
      }
    }
  }
  post { always { archiveArtifacts artifacts: 'diagnostic/**', allowEmptyArchive: true } }
}
'''.replace('LAUNCHER', groovy(launcher)).replace('RUNTIME', inputs['runtime_image_id']).replace('COORDINATOR', inputs['coordinator_sha256'])
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
        private = ROOT / '.local/nas-native-soak' / (case + '-previous-leroy-definition.json')
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
    counts = result['observation'].get('parser_counts') or {}
    qualified = bool(result['observation'].get('started') and result['observation'].get('ended_cleanly')
                     and result['observation'].get('exit_code') == 0 and requests
                     and counts.get('kernel_packets_dropped') == 0 and not counts.get('unparsed_streams')
                     and not counts.get('connection_bound_exceeded'))
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
             'server_boundary_metadata_qualified': qualified,
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


def check_observation_prerequisites(inputs):
    """Validate namespace entry and the kernel filter before any original test."""
    image = inputs['runtime_image_id']
    name = 'leroy-soak-network-probe-0ad540dd5780'
    probe = inner('run', '-d', '--name', name, '--label', 'io.leroy.nas-soak=network-probe',
                  '--network', 'none', '--read-only', '--user', '1000:1000', '--cap-drop', 'ALL',
                  '--security-opt', 'apparmor=graphato-server', '--memory', '64m', '--memory-swap', '64m',
                  '--cpus', '0.1', '--entrypoint', 'python3', image, '-B', '-c', 'import time;time.sleep(120)').strip()
    state = json.loads(inner('inspect', probe))[0]
    assert state['Image'] == image and state['State']['Running']
    program = 'import importlib.util,socket,pathlib,json\n'
    program += 's=importlib.util.spec_from_file_location("observer",' + repr(INNER + '/nas-passive-http.py') + ')\n'
    program += 'm=importlib.util.module_from_spec(s);s.loader.exec_module(m)\n'
    program += 'm.join_fixture_network(' + str(state['State']['Pid']) + ')\n'
    program += 'p=socket.socket(socket.AF_PACKET,socket.SOCK_RAW,socket.htons(0x0800));m.filter_http(p);p.close()\n'
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
        # The observer creates no Docker namespace-sharing dependency. The probe
        # can be removed independently, just like the original test's server.
    finally:
        current = json.loads(inner('inspect', probe))[0]
        assert current['Config']['Labels']['io.leroy.nas-soak'] == 'network-probe'
        inner('rm', '-f', probe)


def main():
    inputs = json.loads((PREPARATION / 'prepared-inputs.json').read_text())
    launcher = (ROOT / 'scripts/diagnostics/nas-soak-launcher.py').read_text()
    definition = jenkins_definition(launcher, inputs)
    assert not FOLDER.exists(), 'Preserve the first complete or partial fixed-order series'
    FOLDER.mkdir(parents=True)
    save(FOLDER / 'plan.json', {'created_at': datetime.now(timezone.utc).isoformat(), 'order': ORDER, 'inputs': inputs,
                              'launcher_sha256': hashlib.sha256(launcher.encode()).hexdigest(), 'test_changes_authorized': False,
                              'full_pipeline_acceptance': False, 'fresh_fixture_per_sample': True, 'implicit_retries': False})
    (FOLDER / 'jenkins-definition.xml').write_text(definition, encoding='utf-8')
    baseline = begin(FOLDER, 'initialize')
    idle()
    state = json.loads(inner('inspect', 'jenkins-parity'))[0]
    original_running = state['State']['Running']
    save(FOLDER / 'jenkins-controller-before.json', {'id': state['Id'], 'running': original_running,
                                                  'memory_bytes': state['HostConfig']['Memory'], 'image': state['Image']})
    results = {}
    try:
        check_observation_prerequisites(inputs)
        if not original_running:
            start_jenkins()
        jobs = json.loads(jenkins_api('/api/json?tree=jobs[name]')['text'])['jobs']
        assert JOB not in {j['name'] for j in jobs}, 'Keep an existing diagnostic job unchanged'
        jenkins_api('/createItem?' + urlencode({'name': JOB}), definition, 'application/xml')
        finish(FOLDER, 'initialize', baseline)
        for case in ORDER:
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
            save(FOLDER / 'jenkins-controller-restored.json', {'id': state['Id'], 'running': False, 'all_samples_same_controller_baseline': True})
        if not inner('ps', '-q', '--filter', 'label=io.graphato.e2e.owner').strip():
            remove_temporary_profile()


if __name__ == '__main__':
    main()

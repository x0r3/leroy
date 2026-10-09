"""Evaluate the separate Soak test-driver proposal; never replace original acceptance."""

import argparse
import base64
import gzip
import hashlib
import json
import subprocess
import tarfile
from contextlib import closing
from pathlib import PurePosixPath

import compare_frozen_postdeploy_group as group
from compare_nas_antares import client
from nas_diagnostic import execute
from nas_gitea_target import idle
from nas_measurement_guard import qualification_report
from nas_ssh import ROOT

COMMIT = '0ad540dd578033d45e4d0c25d89fbe57b32102a4'
NAME = 'frozen-soak-rate-proposal-' + COMMIT[:12]
GUEST = r'''
import base64,gzip,hashlib,importlib.util,json,os,pathlib,re,subprocess,uuid
assert pathlib.Path('/var/lib/leroy-vm/ready').is_file() and os.cpu_count()==4
release=pathlib.Path('/opt/graphato/current').resolve(strict=True)
assert release.parent==pathlib.Path('/opt/graphato/releases')
manifest=json.loads((release/'manifest.json').read_text());assert manifest['commit']==COMMIT
assert manifest['runtimeImageId']==BINDING['runtimeImageId']
assert manifest['files']['verification-source.tar.gz']==BINDING['sourceSha256']
assert manifest['build']['timestamp']==BINDING['buildTimestamp']
with (release/'verification-source.tar.gz').open('rb') as stream:
 assert hashlib.file_digest(stream,'sha256').hexdigest()==BINDING['sourceSha256']
helper=release/'deployments/linux/host/postdeploy.py'
assert hashlib.sha256(helper.read_bytes()).hexdigest()==manifest['files']['deployments/linux/host/postdeploy.py']
spec=importlib.util.spec_from_file_location('separate_soak_retry_proposal',helper)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
original_state=module.STATE
def original_receipts():
 return {suite:(hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None)
         for suite in module.SUITES for p in [original_state/'results'/COMMIT/suite/'result.json']}
before=original_receipts();assert all(value is None for value in before.values())
directory=pathlib.Path('/var/lib/leroy-vm/diagnostics')/NAME
assert not directory.exists()
directory.mkdir(parents=True,mode=0o700)
module.STATE=directory/'private-postdeploy-state'
payload=json.loads(gzip.decompress(base64.b64decode(PAYLOAD,validate=True)))
assert set(payload)==set(PROPOSED_HASHES)==set(ORIGINAL_HASHES)=={'open-runner.mjs','followup-cases.mjs'}
for name,body in payload.items():
 p=directory/'apps/desktop/e2e-web'/name;p.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
 p.write_text(body,encoding='utf-8')
 assert hashlib.sha256(p.read_bytes()).hexdigest()==PROPOSED_HASHES[name]
proofs=[];original_steps=module.check_steps
hash_program="const fs=require('node:fs'),crypto=require('node:crypto');const out={};for(const n of ['open-runner.mjs','followup-cases.mjs'])out[n]=crypto.createHash('sha256').update(fs.readFileSync('/build/apps/desktop/e2e-web/'+n)).digest('hex');console.log(JSON.stringify(out));"
def steps(ci,executor,source,release,manifest,reports):
 original_run=executor.run
 def run(*args,**kwargs):
  result=original_run(*args,**kwargs)
  tag='graphato/web-tests:postdeploy-'+COMMIT
  if args==('docker','image','inspect',tag,'--format','{{.Id}}'):
   base=result.stdout.strip();assert re.fullmatch('sha256:[a-f0-9]{64}',base)
   def hashes(image):
    value=original_run('docker','run','--rm','--read-only','--network','none','--cap-drop','ALL',
       '--security-opt','no-new-privileges','--entrypoint','node',image,'-e',hash_program,capture=True,timeout=30)
    return json.loads(value.stdout)
   assert hashes(base)==ORIGINAL_HASHES
   (directory/'Dockerfile').write_text('FROM '+tag+'\nCOPY --chmod=0644 apps/desktop/e2e-web/*.mjs /build/apps/desktop/e2e-web/\n')
   derived='leroy-diagnostic/graphato-soak-rate-proposal:'+COMMIT[:12]
   original_run('docker','build','--network','none','--pull=false','-t',derived,directory,timeout=300)
   a,b=json.loads(original_run('docker','image','inspect',base,derived,capture=True).stdout)
   assert b['RootFS']['Layers'][:-1]==a['RootFS']['Layers']
   assert all(a['Config'].get(key)==b['Config'].get(key) for key in a['Config'].keys()|b['Config'].keys())
   assert hashes(b['Id'])==PROPOSED_HASHES
   proofs.append({'base_worker_image_id':base,'proposal_worker_image_id':b['Id'],
      'original_worker_layers_retained':True,'one_test_driver_overlay_layer_added':True,
      'original_worker_configuration_retained':True,'original_file_hashes':ORIGINAL_HASHES,
      'proposal_file_hashes':PROPOSED_HASHES})
   return subprocess.CompletedProcess(args,0,stdout=b['Id']+'\n')
  return result
 executor.run=run
 return original_steps(ci,executor,source,release,manifest,reports)
module.check_steps=steps
receipt=module.execute('web',COMMIT,'soak',uuid.uuid4().hex)
assert len(proofs)==1 and set(receipt['checks'])=={'browser-soak'}
assert receipt['cleanupComplete'] and not receipt['reused'] and not receipt['cancelled']
assert all(receipt[key]==value for key,value in BINDING.items())
assert original_receipts()==before,'Do not alter either original suite receipt'
reports=module.result_directory('web',COMMIT)
case=json.loads((reports/'browser-soak/open/results.json').read_text())
archive=directory/'proposal-artifacts.tar.gz'
with archive.open('wb') as stream:module.write_artifacts('web',COMMIT,stream)
with archive.open('rb') as stream:archive_sha=hashlib.file_digest(stream,'sha256').hexdigest()
output={'commit':COMMIT,'binding':BINDING,'target_cpus':4,'receipt':receipt,'soak_case':case,
 'image_proof':proofs[0],'patch_sha256':PATCH_SHA,'artifact_archive_sha256':archive_sha,
 'original_receipts_before_and_after':before,'original_acceptance_result_replaced':False,
 'test_driver_source_changed':True,'application_runtime_source_changed':False,
 'application_rate_limits_changed':False,'production_modified':False,'production_replacement_ready':False,
 'scope':'One separate NAS Soak evaluation with two proposed test-driver files; not original-image acceptance or Jenkins parity'}
(directory/'proposal-result.json').write_text(json.dumps(output,indent=2)+'\n')
print(json.dumps(output))
'''


def analyze(folder, run):
    artifact_root = folder / 'leroy-artifacts/probe'
    result_path = artifact_root / 'proposal-result.json'
    archive_path = artifact_root / 'proposal-artifacts.tar.gz'
    value = group.read(result_path)
    assert run['status'] == 'succeeded', 'Diagnostic collection must complete before evaluating its workload'
    assert value['test_driver_source_changed'] and not value['original_acceptance_result_replaced']
    assert not value['application_runtime_source_changed'] and not value['application_rate_limits_changed']
    with archive_path.open('rb') as stream:
        assert hashlib.file_digest(stream, 'sha256').hexdigest() == value['artifact_archive_sha256']
    selected, names = {}, set()
    wanted = {'result.json', 'browser-soak.log', 'browser-soak/open/results.json'}
    with tarfile.open(archive_path) as archive:
        for member in archive:
            name = PurePosixPath(member.name)
            assert member.isfile() and 0 <= member.size <= 64 * 1024**2
            assert not name.is_absolute() and '..' not in name.parts and member.name not in names
            names.add(member.name)
            assert len(names) < 1000
            if member.name in wanted:
                selected[member.name] = archive.extractfile(member).read()
    assert selected.keys() == wanted
    receipt = json.loads(selected['result.json'])
    cases = json.loads(selected['browser-soak/open/results.json'])
    assert receipt == value['receipt'] and cases == value['soak_case']
    assert len(cases) == 1 and cases[0]['id'] == 'soak'
    passed = receipt['requestedPassed']
    assert passed == receipt['checks']['browser-soak']['passed'] == cases[0]['passed']
    metrics = []
    for line in selected['browser-soak.log'].decode(errors='replace').splitlines():
        try:
            row = json.loads(line[line.index('{'):])
        except (ValueError, TypeError):
            continue
        if isinstance(row, dict) and row.get('event') == 'boundedSoak':
            metrics.append(row)
    if passed:
        metric, = metrics
        assert metric['tabs'] == 4 and metric['prompts'] == 120 and metric['durationSeconds'] >= 300
        assert metric['failedResponses'] == 0 and metric['polls'] > 10 and metric['nativeRateLimits'] < 12
        assert metric['statuses'].get('429', 0) < metric['polls'] / 10
        assert metric['secondsSinceLastRateLimit'] is None or metric['secondsSinceLastRateLimit'] > 30
    report = {'at': group.timestamp(), 'run_id': run['id'], 'proposal_soak_passed': passed,
              **qualification_report(folder, ('diagnostic',)),
              'metrics': metrics, 'case_result': cases[0], 'binding': value['binding'],
              'image_proof': value['image_proof'], 'patch_sha256': value['patch_sha256'],
              'artifact_archive_sha256': value['artifact_archive_sha256'],
              'test_driver_source_changed': True, 'application_runtime_source_changed': False,
              'application_rate_limits_changed': False, 'original_acceptance_result_replaced': False,
              'original_receipts_before_and_after': value['original_receipts_before_and_after'],
              'target_cpus': 4, 'production_replacement_ready': False,
              'scope': 'One modified-driver Soak group; no original full release or Jenkins parity claim'}
    group.write(folder / 'analysis.json', report)
    print(json.dumps({'separate_proposal_soak_passed': passed, 'metrics': metrics,
                      'original_acceptance_result_replaced': False, 'production_replacement_ready': False}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--resume', action='store_true', help='Collect the identical retained diagnostic run')
    args = parser.parse_args()
    base = ROOT / 'test-results/nas-parity/followup/candidates/graphato' / COMMIT
    folder = ROOT / 'test-results/nas-parity/followup' / NAME
    assert not (args.resume and args.prepare_only)
    proposal = ROOT / '.local/graphato-native-rate-proposal'
    proof = group.read(proposal / 'proposal.json')
    patch = ROOT / 'docs/upstream-patches/graphato-soak-rate-handling-proposal.patch'
    assert proof['base_commit'] == COMMIT and hashlib.sha256(patch.read_bytes()).hexdigest() == proof['proposal_patch_sha256']
    checkout = ROOT / '.sources/frozen-master/graphato-0ad540dd5780'
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=checkout, text=True).strip() == COMMIT
    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=checkout)
    payload = {path.name: path.read_text(encoding='utf-8')
               for path in (proposal / 'apps/desktop/e2e-web').glob('*.mjs')}
    proposed = {name: hashlib.sha256(body.encode()).hexdigest() for name, body in payload.items()}
    original = {name: hashlib.sha256(subprocess.check_output(
        ['git', 'show', COMMIT + ':apps/desktop/e2e-web/' + name], cwd=checkout)).hexdigest() for name in payload}
    assert len(payload) == 2
    transport = base64.b64encode(gzip.compress(json.dumps(payload).encode(), mtime=0)).decode()
    manifest = group.read(base / 'controlled-groups/full-release-leroy-cpu-eight-round-1/leroy-target-before.json')['manifest']
    binding = {'runtimeImageId': manifest['runtimeImageId'],
               'sourceSha256': manifest['files']['verification-source.tar.gz'],
               'buildTimestamp': manifest['build']['timestamp']}
    prefix = {'COMMIT': COMMIT, 'NAME': NAME, 'PAYLOAD': transport, 'PROPOSED_HASHES': proposed,
              'ORIGINAL_HASHES': original, 'BINDING': binding, 'PATCH_SHA': proof['proposal_patch_sha256']}
    guest = '\n'.join(key + '=' + repr(value) for key, value in prefix.items()) + '\n' + GUEST
    # Stream browser artifacts separately rather than put their bytes in a log.
    fetch = "import pathlib,sys\np=pathlib.Path('/var/lib/leroy-vm/diagnostics/" + NAME + "/proposal-artifacts.tar.gz')\n"
    fetch += "assert p.is_file() and p.stat().st_size <= 256*1024**2\nwith p.open('rb') as f: __import__('shutil').copyfileobj(f,sys.stdout.buffer)\n"
    program = "import hashlib,json,pathlib,re,subprocess\nfrom leroy.actions import required,ssh_args\n"
    program += "command=ssh_args('graphato-vm','root',12225,required('BOOTSTRAP_KEY'),required('KNOWN_HOSTS'))\n"
    program += "r=subprocess.run([*command,'python3 -B -'],input=" + repr(guest) + ",text=True,capture_output=True,timeout=4200)\n"
    program += "if r.returncode:\n"
    program += " pathlib.Path('failure.json').write_text(json.dumps({'exit_code':r.returncode,'stdout_sha256':hashlib.sha256(r.stdout.encode()).hexdigest(),'stderr_sha256':hashlib.sha256(r.stderr.encode()).hexdigest(),'exception_types':re.findall(r'^([A-Za-z]+Error):',r.stderr,re.MULTILINE)},indent=2)+'\\n')\n"
    program += " raise SystemExit('Separate proposal diagnostic failed before receipt collection')\n"
    program += "value=json.loads(r.stdout)\npathlib.Path('proposal-result.json').write_text(json.dumps(value,indent=2)+'\\n')\n"
    program += "with pathlib.Path('proposal-artifacts.tar.gz').open('wb') as stream:\n"
    program += " subprocess.run([*command,'python3 -B -'],input=" + repr(fetch.encode()) + ",stdout=stream,stderr=subprocess.PIPE,check=True,timeout=120)\n"
    program += "with pathlib.Path('proposal-artifacts.tar.gz').open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==value['artifact_archive_sha256']\n"
    program += "print(json.dumps({'proposal_soak_requested_passed':value['receipt']['requestedPassed'],'original_acceptance_replaced':False,'production_replacement_ready':False}),flush=True)\n"
    assert len(program) <= 32768
    compile(program, 'separate rate proposal dispatcher', 'exec')
    prepared = {'commit': COMMIT, 'target_cpus': 4, 'binding': binding,
                'patch_sha256': proof['proposal_patch_sha256'], 'original_file_hashes': original,
                'proposed_file_hashes': proposed, 'test_driver_source_changed': True,
                'original_acceptance_result_replaced': False, 'production_replacement_ready': False}
    folder.mkdir(parents=True, exist_ok=True)
    marker = folder / 'prepared.json'
    if marker.exists():
        existing = group.read(marker)
        assert all(existing[key] == value for key, value in prepared.items())
    else:
        group.write(marker, {'at': group.timestamp(), **prepared})
    if args.prepare_only:
        print(json.dumps({'prepared': True, 'nas_run_started': False, 'dispatcher_chars': len(program)}))
        return
    if args.resume:
        assert (folder / 'run-id.json').is_file()
    else:
        assert not (folder / 'run-id.json').exists(), 'Retain the first proposal evaluation; no implicit rerun'
        # A changed test driver cannot waive a failed complete original release.
        original_release = group.read(base / 'controlled-groups/full-release-leroy-cpu-eight-round-1/analysis.json')
        assert original_release['all_29_original_groups_executed_under_leroy']
        idle()
        scenario = group.read(base / 'scenarios/root-private-existing-host/scenario.json')
        if not (folder / 'leroy-target-before.json').exists():
            group.restore(folder, 'leroy', COMMIT, scenario['baseline_snapshot'])
    with closing(client()) as api:
        previous = next(row['spec'] for row in api.get('/api/pipelines').json() if row['id'] == 'leroy-nas-diagnostics')
    try:
        _, run = execute(NAME, program, secrets=('graphato-bootstrap',), timeout=4260,
                         artifacts=('proposal-result.json', 'proposal-artifacts.tar.gz', 'failure.json'), profile='graphato')
    finally:
        with closing(client()) as api:
            api.put('/api/pipelines/leroy-nas-diagnostics', json=previous).raise_for_status()
            assert not any(row['enabled'] for row in api.get('/api/pipelines').json())
    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=checkout)
    analyze(folder, run)


if __name__ == '__main__':
    main()

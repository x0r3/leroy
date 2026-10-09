"""Observe original soak HTTP metadata in an explicitly separate diagnostic worker image."""

import argparse
import hashlib
import json
import re
from contextlib import closing

from compare_nas_antares import client
from nas_diagnostic import execute
from nas_ssh import ROOT

GUEST = r'''
import hashlib,importlib.util,json,os,pathlib,subprocess,uuid
assert pathlib.Path('/var/lib/leroy-vm/ready').is_file()
assert os.cpu_count()==4,'Record the initial HTTP observation at the original four-CPU allocation'
release=pathlib.Path('/opt/graphato/current').resolve(strict=True)
assert release.parent==pathlib.Path('/opt/graphato/releases')
manifest=json.loads((release/'manifest.json').read_text());assert manifest['commit']==COMMIT
with (release/'verification-source.tar.gz').open('rb') as stream:
 assert hashlib.file_digest(stream,'sha256').hexdigest()==manifest['files']['verification-source.tar.gz']
helper=release/'deployments/linux/host/postdeploy.py'
assert hashlib.sha256(helper.read_bytes()).hexdigest()==manifest['files']['deployments/linux/host/postdeploy.py']
spec=importlib.util.spec_from_file_location('original_soak_http_diagnostic',helper)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
directory=module.STATE/'leroy-diagnostics'/DIAGNOSTIC_NAME
assert not directory.exists() and not (module.result_directory('web',COMMIT)/'result.json').exists()
directory.mkdir(parents=True,mode=0o700)
(directory/'observer.mjs').write_text(OBSERVER)
assert hashlib.sha256((directory/'observer.mjs').read_bytes()).hexdigest()==OBSERVER_SHA
original_steps=module.check_steps;image_proofs=[]
def steps(ci,executor,source,release,manifest,reports):
 original_run=executor.run
 def run(*args,**kwargs):
  result=original_run(*args,**kwargs)
  tag='graphato/web-tests:postdeploy-'+COMMIT
  if args==('docker','image','inspect',tag,'--format','{{.Id}}'):
   base=result.stdout.strip();assert re.fullmatch(r'sha256:[a-f0-9]{64}',base)
   (directory/'Dockerfile').write_text('FROM '+tag+'\nCOPY --chmod=0644 observer.mjs /usr/local/lib/leroy-http-diagnostic.mjs\nENV NODE_OPTIONS=--import=/usr/local/lib/leroy-http-diagnostic.mjs\n')
   derived='leroy-diagnostic/graphato-web-http:'+COMMIT[:12]+'-attempt-'+str(ATTEMPT)
   original_run('docker','build','--network','none','--pull=false','-t',derived,directory,timeout=300)
   images=json.loads(original_run('docker','image','inspect',base,derived,capture=True).stdout)
   a,b=images;assert b['RootFS']['Layers'][:-1]==a['RootFS']['Layers']
   assert {k:v for k,v in a['Config'].items() if k!='Env'}=={k:v for k,v in b['Config'].items() if k!='Env'}
   assert {e for e in b['Config']['Env'] if not e.startswith('NODE_OPTIONS=')}==set(a['Config']['Env'])
   image_proofs.append({'base_worker_image_id':base,'diagnostic_worker_image_id':b['Id'],
     'original_layers_preserved':True,'one_observer_layer_added':True,'application_test_files_modified':False,
     'node_options':'One metadata observer preload; fetch/browser arguments and results are forwarded unchanged'})
   return subprocess.CompletedProcess(args,0,stdout=b['Id']+'\n')
  return result
 executor.run=run
 return original_steps(ci,executor,source,release,manifest,reports)
module.check_steps=steps
result=module.execute('web',COMMIT,'soak',uuid.uuid4().hex)
reports=module.result_directory('web',COMMIT)
data=(reports/'browser-soak/open/leroy-http-metadata.log').read_bytes()
assert len(data)<32*1024**2 and len(image_proofs)==1
rows=[json.loads(line) for line in data.splitlines()]
assert rows[0]['kind']=='diagnostic-start'
assert any(row['kind']=='observer-ready' for row in rows)
assert rows[-1]['kind']=='diagnostic-end' and rows[-1]['dropped']==0
assert result['cleanupComplete'] and not result['cancelled'] and not result['reused']
assert set(result['checks'])=={'browser-soak'}
output={'commit':COMMIT,'result':result,'image_proof':image_proofs[0],
 'observer_sha256':OBSERVER_SHA,'http_metadata_sha256':hashlib.sha256(data).hexdigest(),
 'application_source_changed':False,'application_rate_limits_changed':False,
 'original_acceptance_result_replaced':False,'production_replacement_ready':False,
 'scope':'Supporting metadata observation with a derived test-worker image; not original-image acceptance'}
with (directory/'artifacts.tar.gz').open('wb') as stream:module.write_artifacts('web',COMMIT,stream)
(directory/'result.json').write_text(json.dumps(output,indent=2)+'\n')
print(json.dumps({'summary':output,'metadata':rows}))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--resume', action='store_true', help='Observe the identical retained run; never start another')
    parser.add_argument('--attempt', type=int, choices=[1, 2, 3], default=1)
    parser.add_argument('--reason', help='Required explanation for a distinct diagnostic repair attempt')
    args = parser.parse_args()
    assert re.fullmatch('[a-f0-9]{40}', args.commit)
    observer_path = ROOT / 'scripts/diagnostics/nas-browser-http.mjs'
    observer = observer_path.read_text(encoding='utf-8')
    observer_sha = hashlib.sha256(observer.encode()).hexdigest()
    name = 'frozen-soak-http-' + args.commit[:12]
    if args.attempt > 1:
        assert args.reason, 'Explain and retain the previous failed diagnostic before a repair attempt'
        prior = ROOT / ('test-results/nas-parity/followup/' + name +
                        (('-attempt-' + str(args.attempt - 1)) if args.attempt > 2 else ''))
        assert json.loads((prior / 'run.json').read_text())['status'] == 'failed'
        name += '-attempt-' + str(args.attempt)
    folder = ROOT / 'test-results/nas-parity/followup' / name
    assert not folder.exists() or args.resume, 'Preserve first diagnostic; use --resume only for identical observation'
    if args.resume:
        assert (folder / 'run-id.json').is_file(), 'No recorded run to resume'
    guest = 'import re\nCOMMIT=' + repr(args.commit) + '\nOBSERVER=' + repr(observer)
    guest += '\nDIAGNOSTIC_NAME=' + repr(name) + '\nATTEMPT=' + repr(args.attempt)
    guest += '\nOBSERVER_SHA=' + repr(observer_sha) + '\n' + GUEST
    compile(guest, 'original soak metadata observer', 'exec')
    program = ("import json,pathlib,subprocess\nfrom leroy.actions import required,ssh_args\n"
               "command=ssh_args('graphato-vm','root',12225,required('BOOTSTRAP_KEY'),required('KNOWN_HOSTS'))\n"
               "result=subprocess.run([*command,'python3 -B -'],input=" + repr(guest) +
               ",text=True,capture_output=True,timeout=4200)\n"
               "if result.returncode:\n"
               " import hashlib,re\n"
               " failure={'exit_code':result.returncode,'stdout_sha256':hashlib.sha256(result.stdout.encode()).hexdigest(),"
               "'stderr_sha256':hashlib.sha256(result.stderr.encode()).hexdigest(),"
               "'exception_types':re.findall(r'^([A-Za-z]+Error):',result.stderr,re.MULTILINE),"
               "'traceback_locations':[{'file':pathlib.PurePosixPath(p).name,'line':int(n)} "
               "for p,n in re.findall(r'^  File \"([^\"]+)\", line (\\d+)',result.stderr,re.MULTILINE)[-4:]]}\n"
               " pathlib.Path('failure.json').write_text(json.dumps(failure,indent=2)+'\\n')\n"
               " print('Metadata observation failed',result.returncode,flush=True); raise SystemExit(1)\n"
               "value=json.loads(result.stdout)\n"
               "pathlib.Path('result.json').write_text(json.dumps(value['summary'],indent=2)+'\\n')\n"
               "pathlib.Path('http-metadata.jsonl').write_text(''.join(json.dumps(row)+'\\n' for row in value['metadata']))\n"
               "print(json.dumps({'metadata_rows':len(value['metadata']),"
               "'original_soak_requested_passed':value['summary']['result']['requestedPassed']}),flush=True)\n")
    compile(program, 'NAS HTTP metadata diagnostic dispatcher', 'exec')
    if not folder.exists():
        folder.mkdir(parents=True)
        (folder / 'attempt.json').write_text(json.dumps(
            {'attempt': args.attempt, 'reason': args.reason, 'previous_failure_preserved': args.attempt > 1,
             'application_or_original_tests_changed': False}, indent=2) + '\n')
    with closing(client()) as api:
        previous = next(row['spec'] for row in api.get('/api/pipelines').json()
                        if row['id'] == 'leroy-nas-diagnostics')
    try:
        execute(name, program, secrets=('graphato-bootstrap',), timeout=4260,
                artifacts=('result.json', 'http-metadata.jsonl', 'failure.json'), profile='graphato')
    finally:
        with closing(client()) as api:
            api.put('/api/pipelines/leroy-nas-diagnostics', json=previous).raise_for_status()
            assert not any(row['enabled'] for row in api.get('/api/pipelines').json())


if __name__ == '__main__':
    main()

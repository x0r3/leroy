"""Update only the owned job images after the frozen comparison has completed."""

import hashlib
import json
import tarfile
from datetime import datetime, timezone

from deploy_nas_parity import CREDENTIALS, LOCAL, REMOTE
from nas_gitea_target import idle
from nas_ssh import ROOT, run_script, upload_file
from stage_nas_production_graphato import COMMIT

PROGRAM = r'''
import hashlib,json,pathlib,re,subprocess
root=pathlib.Path('/volume1/docker/leroy-nas-parity');assert (root/'.leroy-owned').is_file()
outer=json.loads(subprocess.check_output(['docker','inspect','leroy-nas-parity-docker-1'],text=True))[0]
assert outer['Id']=='7d029e17dc28b04ec41ac927360062f057c97564227c62e7e01a50a4938b5a00'
prefix=['docker','exec','-i',outer['Id'],'docker']
assert subprocess.check_output(prefix+['inspect','jenkins-parity','--format','{{.State.Running}}'],text=True).strip()=='false'
assert not subprocess.check_output(prefix+['ps','-a','--filter','label=io.leroy.runner=runner-nas-parity','-q'],text=True).strip()
profile=root/'config/runner.toml';before_config=hashlib.sha256(profile.read_bytes()).hexdigest()
context='/var/lib/docker/leroy-child-failure-reason'
with (root/'child-failure-reason.tar').open('rb') as source:
 subprocess.run(['docker','exec','-i',outer['Id'],'sh','-c','mkdir '+context+' && tar -xf - -C '+context],stdin=source,check=True,timeout=30)
rows={}
for tag,expected in PREVIOUS.items():
 old=json.loads(subprocess.check_output(prefix+['image','inspect',tag],text=True))[0]
 assert old['Id']==expected
 backup=tag+'-before-child-failure-reason'
 assert subprocess.run(prefix+['image','inspect',backup],capture_output=True).returncode!=0
 subprocess.run(prefix+['tag',old['Id'],backup],check=True)
 args=['run','--rm','--network','none','--memory','128m','--memory-swap','128m','--cpus','0.5',tag,'python','-c']
 destination=subprocess.check_output(prefix+args+['import leroy.worker;print(leroy.worker.__file__)'],text=True,timeout=30).strip()
 assert re.fullmatch(r'/(usr/local|opt/leroy-worker)/lib/python3\.\d+/site-packages/leroy/worker\.py',destination)
 subprocess.run(prefix+['build','--network=none','--pull=false','-t',tag,'-f','-',context],input='FROM '+backup+'\nCOPY worker.py '+destination+'\n',text=True,check=True,stdout=subprocess.DEVNULL,timeout=240)
 new=json.loads(subprocess.check_output(prefix+['image','inspect',tag],text=True))[0]
 assert old['Config']==new['Config'] and old['RootFS']['Layers']==new['RootFS']['Layers'][:-1]
 actual=subprocess.check_output(prefix+args+['import hashlib,leroy.worker;print(hashlib.sha256(open(leroy.worker.__file__,"rb").read()).hexdigest())'],text=True,timeout=30).strip()
 assert actual==EXPECTED
 rows[tag]={'before':old['Id'],'after':new['Id'],'worker_sha256':actual,'dependencies_unchanged':True,'image_config_unchanged':True}
assert hashlib.sha256(profile.read_bytes()).hexdigest()==before_config
print('EVIDENCE='+json.dumps({'images':rows,'profiles_unchanged':True,'controller_and_runner_not_restarted':True,'lease_seconds_unchanged':90,'production_modified':False}))
'''


def main():
    base = ROOT / 'test-results/nas-parity/followup'
    destination = base / 'child-failure-reason-deployment.json'
    assert not destination.exists(), 'No implicit repeat of an image update'
    completed = base / 'candidates/graphato' / COMMIT / 'scenarios/root-private-existing-host/analysis.json'
    comparison = json.loads(completed.read_text())
    assert comparison['all_required_groups_executed_both'] and not comparison['application_patches_applied']
    idle()
    proof = json.loads((base / 'child-failure-reason-tests.json').read_text())
    assert proof['passed'] and proof['postgresql_real'] and '102 passed' in proof['output']
    expected = hashlib.sha256((ROOT / 'src/leroy/worker.py').read_bytes()).hexdigest()
    assert expected == proof['worker_sha256']
    previous = json.loads((completed.parents[2] / 'control-residency-deployment.json').read_text())
    tags = ('leroy-job:nas-parity', 'leroy-job:nas-parity-gitea')
    archive = LOCAL / 'child-failure-reason.tar'
    with tarfile.open(archive, 'w') as bundle:
        bundle.add(ROOT / 'src/leroy/worker.py', arcname='worker.py')
    upload_file(archive, REMOTE + '/' + archive.name, CREDENTIALS)
    values = {'EXPECTED': expected, 'PREVIOUS': {tag: previous['images'][tag]['after'] for tag in tags}}
    program = '\n'.join(name + '=' + repr(value) for name, value in values.items()) + '\n' + PROGRAM
    result = run_script("python3 - <<'PY'\n" + program + '\nPY\n', CREDENTIALS, timeout=600)
    assert result.returncode == 0, result.stderr[-2000:]
    record = json.loads(next(line[9:] for line in result.stdout.splitlines() if line.startswith('EVIDENCE=')))
    record.update(at=datetime.now(timezone.utc).isoformat(), tests_evidence='test-results/nas-parity/followup/child-failure-reason-tests.json',
                  completed_comparison_worker_changed=False, application_patches_applied=False,
                  new_nested_failure_and_ui_validation_pending=True)
    destination.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record), flush=True)


if __name__ == '__main__':
    main()

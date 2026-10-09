"""Deploy verified supervisor/lease diagnostics and keep only job-control processes out of swap."""

import hashlib
import json
import subprocess
import sys
import tarfile
import tomllib
from datetime import datetime, timezone

from deploy_nas_parity import CREDENTIALS, LOCAL, REMOTE
from nas_gitea_target import idle
from nas_ssh import ROOT, run_script, upload_file
from stage_nas_production_graphato import COMMIT

PROGRAM = r'''
import hashlib,json,pathlib,re,shutil,subprocess
root=pathlib.Path('/volume1/docker/leroy-nas-parity');assert (root/'.leroy-owned').is_file()
outer=json.loads(subprocess.check_output(['docker','inspect','leroy-nas-parity-docker-1'],text=True))[0]
assert outer['Id']=='7d029e17dc28b04ec41ac927360062f057c97564227c62e7e01a50a4938b5a00'
assert outer['HostConfig']['Memory']==4831838208 and outer['HostConfig']['MemorySwap']==8053063680
inner=['docker','exec','-i',outer['Id'],'docker']
assert subprocess.check_output(inner+['inspect','jenkins-parity','--format','{{.State.Running}}'],text=True).strip()=='false'
assert not subprocess.check_output(inner+['ps','-a','--filter','label=io.leroy.runner=runner-nas-parity','-q'],text=True).strip()
profile=root/'config/runner.toml';assert hashlib.sha256(profile.read_bytes()).hexdigest()==CONFIG_BEFORE
folder=root/'control-residency';assert not folder.exists();folder.mkdir()
subprocess.run(['tar','-xf',str(root/'control-residency.tar'),'-C',str(folder)],check=True)
for name,digest in EXPECTED.items():assert hashlib.sha256((folder/name).read_bytes()).hexdigest()==digest
context='/var/lib/docker/leroy-control-residency'
with (root/'control-residency.tar').open('rb') as source:
 subprocess.run(['docker','exec','-i',outer['Id'],'sh','-c','mkdir '+context+' && tar -xf - -C '+context],stdin=source,check=True,timeout=30)
rows={}
for tag,prefix,module,build_context in [('leroy-runner:nas-parity',['docker'],'runner',str(folder)),('leroy-job:nas-parity',inner,'worker',context),('leroy-job:nas-parity-gitea',inner,'worker',context)]:
 old=json.loads(subprocess.check_output(prefix+['image','inspect',tag],text=True))[0]
 backup=tag+'-before-control-residency'
 assert subprocess.run(prefix+['image','inspect',backup],capture_output=True).returncode!=0
 subprocess.run(prefix+['tag',old['Id'],backup],check=True)
 target=subprocess.check_output(prefix+['run','--rm','--network','none','--memory','128m','--memory-swap','128m',tag,'python','-c','import leroy.'+module+';print(leroy.'+module+'.__file__)'],text=True,timeout=30).strip()
 assert re.fullmatch(r'/(usr/local|opt/leroy-worker)/lib/python3\.\d+/site-packages/leroy/'+module+r'\.py',target)
 dockerfile='FROM '+backup+'\nCOPY '+module+'.py '+target+'\n'
 subprocess.run(prefix+['build','--network=none','--pull=false','-t',tag,'-f','-',build_context],input=dockerfile,text=True,check=True,stdout=subprocess.DEVNULL,timeout=240)
 new=json.loads(subprocess.check_output(prefix+['image','inspect',tag],text=True))[0]
 assert old['Config']==new['Config'] and old['RootFS']['Layers']==new['RootFS']['Layers'][:-1]
 code='import hashlib,leroy.'+module+';print(hashlib.sha256(open(leroy.'+module+'.__file__,"rb").read()).hexdigest())'
 actual=subprocess.check_output(prefix+['run','--rm','--network','none','--memory','128m','--memory-swap','128m',tag,'python','-c',code],text=True,timeout=30).strip()
 assert actual==EXPECTED[module+'.py']
 rows[tag]={'before':old['Id'],'after':new['Id'],'module_sha256':actual,'dependencies_unchanged':True,'image_config_unchanged':True}
staged=root/'config/runner-control-residency.toml';assert hashlib.sha256(staged.read_bytes()).hexdigest()==CONFIG_AFTER
backup=profile.with_name('runner.toml.before-control-residency');assert not backup.exists();shutil.copy2(profile,backup)
shutil.copyfile(staged,profile);profile.chmod(0o644)
subprocess.run(['docker','compose','up','-d','--no-deps','runner'],cwd=root,check=True,timeout=120)
assert subprocess.check_output(['docker','inspect','leroy-nas-parity-runner-1','--format','{{.Image}}'],text=True).strip()==rows['leroy-runner:nas-parity']['after']
print('EVIDENCE='+json.dumps({'images':rows,'graphato_job_memory_bytes':2147483648,'graphato_job_swap_limit_bytes':0,'original_builder_memory_bytes':4294967296,'original_builder_swap_limit_bytes':2147483648,'parent_resource_limits_changed':False,'controller_and_postgres_changed':False,'lease_seconds_unchanged':90,'application_patches_applied':False,'production_modified':False}))
'''


def main():
    destination = ROOT / 'test-results/nas-parity/followup/candidates/graphato' / COMMIT / 'control-residency-deployment.json'
    assert not destination.exists(), 'Retain the first correction deployment'
    idle()
    checked = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'scripts/test_postgres.py')], cwd=ROOT, capture_output=True, text=True)
    proof = {'at': datetime.now(timezone.utc).isoformat(), 'passed': checked.returncode == 0,
             'postgresql_real': True, 'output': checked.stdout + checked.stderr,
             'source_sha256': {name + '.py': hashlib.sha256((ROOT / 'src/leroy' / (name + '.py')).read_bytes()).hexdigest() for name in ('runner', 'worker')}}
    destination.with_name('control-residency-tests.json').write_text(json.dumps(proof, indent=2) + '\n')
    assert proof['passed'] and 'skipped' not in proof['output'], proof['output'][-1500:]
    config = LOCAL / 'config/runner.toml'
    before = config.read_bytes()
    text = config.read_text()
    old = tomllib.loads(text)
    assert old['profiles']['graphato']['memory'] == '2g' and 'memory_swap' not in old['profiles']['graphato']
    assert text.count('[profiles.graphato]') == 1
    updated = text.replace('[profiles.graphato]', '[profiles.graphato]\nmemory_swap = "2g"', 1)
    expected = json.loads(json.dumps(old))
    expected['profiles']['graphato']['memory_swap'] = '2g'
    assert tomllib.loads(updated) == expected
    staged = LOCAL / 'config/runner-control-residency.toml'
    staged.write_text(updated)
    upload_file(staged, REMOTE + '/config/' + staged.name, CREDENTIALS)
    archive = LOCAL / 'control-residency.tar'
    with tarfile.open(archive, 'w') as bundle:
        for name in proof['source_sha256']:
            bundle.add(ROOT / 'src/leroy' / name, arcname=name)
    upload_file(archive, REMOTE + '/' + archive.name, CREDENTIALS)
    values = {'EXPECTED': proof['source_sha256'], 'CONFIG_BEFORE': hashlib.sha256(before).hexdigest(),
              'CONFIG_AFTER': hashlib.sha256(staged.read_bytes()).hexdigest()}
    program = '\n'.join(key + '=' + repr(value) for key, value in values.items()) + '\n' + PROGRAM
    result = run_script("python3 - <<'PY'\n" + program + '\nPY\n', CREDENTIALS, timeout=600)
    assert result.returncode == 0, result.stderr[-2000:]
    record = json.loads(next(line[9:] for line in result.stdout.splitlines() if line.startswith('EVIDENCE=')))
    (LOCAL / 'config/runner-before-control-residency.toml').write_bytes(before)
    config.write_bytes(staged.read_bytes())
    record.update(at=datetime.now(timezone.utc).isoformat(), source_sha256=proof['source_sha256'],
                  tests_evidence=destination.with_name('control-residency-tests.json').relative_to(ROOT).as_posix(),
                  effectiveness_requires_original_workload_rerun=True)
    destination.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record), flush=True)


if __name__ == '__main__':
    main()

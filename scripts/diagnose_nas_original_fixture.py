"""Inspect original frozen fixture startup without running or editing its tests."""

import json
from datetime import datetime, timezone

from nas_gitea_target import idle
from nas_measurement_guard import begin, finish
from nas_ssh import ROOT, run_script
from prepare_nas_native_soak import INNER, REMOTE

PROGRAM = r'''
import hashlib,importlib.util,json,os,pathlib,subprocess,uuid
assert pathlib.Path('/volume1/docker/leroy-nas-parity/.leroy-owned').is_file()
prefix=['docker','exec','leroy-nas-parity-docker-1']
def call(*args,timeout=60):return subprocess.check_output([*prefix,*args],text=True,timeout=timeout).strip()
stage=pathlib.Path(REMOTE)
inputs=json.loads((stage/'inputs.json').read_text())
assert inputs['commit']=='0ad540dd578033d45e4d0c25d89fbe57b32102a4'
profile=stage/'source/deployments/linux/host/graphato-server.apparmor'
assert hashlib.sha256(profile.read_bytes()).hexdigest()==inputs['apparmor_profile_sha256']
before=set(pathlib.Path('/sys/kernel/security/apparmor/profiles').read_text().splitlines())
assert not any(x.startswith('graphato-server ') for x in before)
call('apparmor_parser','-a','-T',INNER+'/source/deployments/linux/host/graphato-server.apparmor')
assert set(pathlib.Path('/sys/kernel/security/apparmor/profiles').read_text().splitlines())==before|{'graphato-server (enforce)'}
node=r"""
import { readFile,writeFile } from 'node:fs/promises';
import { buildDockerImage,prepareState,startStack,cleanup,writeLogs,docker } from './scripts/e2e-docker-server.mjs';
const state=await prepareState(process.env.GRAPHATO_WEB_E2E_ARTIFACTS,await buildDockerImage());
let ready=false,error=null;
try { await startStack(state);ready=true; } catch(e) { error={name:e.name,message:e.message}; }
finally {
 const secrets=await Promise.all(['server-token','postgres-password'].map(n=>readFile(state.secrets+'/'+n,'utf8')));
 const redact=s=>secrets.reduce((v,x)=>v.replaceAll(x.trim(),'[REDACTED]'),s);
 const ids=(await docker(['ps','-aq','--filter','label=com.docker.compose.project='+state.project])).trim().split(/\s+/).filter(Boolean);
 const details=[];
 for(const id of ids) {
  const c=JSON.parse(await docker(['inspect',id]))[0];
  const service=c.Config.Labels['com.docker.compose.service'];
  const logs=redact(await docker(['logs','--tail','120',id],{captureStderr:true}));
  details.push({id,service,image:c.Image,state:c.State,networks:c.NetworkSettings.Networks,
   limits:Object.fromEntries(['Memory','MemorySwap','NanoCpus','PidsLimit'].map(k=>[k,c.HostConfig[k]])),logs});
 }
 const networks=(await docker(['network','ls','-q','--filter','label=com.docker.compose.project='+state.project])).trim().split(/\s+/).filter(Boolean);
 const networkDetails=networks.length?JSON.parse(await docker(['network','inspect',...networks])):[];
 await writeLogs(state);
 await writeFile(state.artifacts+'/startup-diagnostic.json',JSON.stringify({ready,error,containers:details,networks:networkDetails,originalTestsExecuted:false},null,2));
 await cleanup(state);
}
console.log(JSON.stringify({fixtureReady:ready,originalTestsExecuted:false,cleanupComplete:true}));
"""
inner_program='INNER='+repr(INNER)+'\nATTEMPT='+repr(ATTEMPT)+'\nNODE='+repr(node)+'\n'+r"""
import hashlib,importlib.util,json,os,pathlib,subprocess,uuid
root=pathlib.Path(INNER);inputs=json.loads((root/'inputs.json').read_text())
work=root/'startup-diagnostics'/ATTEMPT
assert not work.exists();work.mkdir(parents=True,mode=0o755)
helper=root/'source/deployments/linux/host/postdeploy.py'
assert hashlib.sha256(helper.read_bytes()).hexdigest()==inputs['helper_sha256']
s=importlib.util.spec_from_file_location('original_host',helper);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
m.source_extract(root/'verification-source.tar.gz',work/'source')
for name in ['home','tmp','docker-config','artifacts','e2e-state']:
 p=work/name;p.mkdir(mode=0o700);os.chown(p,1000,1000)
env={'GRAPHATO_E2E_SERVER_IMAGE':inputs['runtime_image_id'],'GRAPHATO_E2E_HOST_POSTDEPLOY':'1',
 'GRAPHATO_E2E_CI_PARENT':'graphato-ci-check-'+uuid.uuid4().hex[:12],
 'XDG_STATE_HOME':str(work/'e2e-state'),'GRAPHATO_WEB_E2E_ARTIFACTS':str(work/'artifacts')}
cmd=m.runner_command(inputs['runtime_image_id'],work,env['GRAPHATO_E2E_CI_PARENT'],env)
r=subprocess.run([*cmd,'--input-type=module','-e',NODE],capture_output=True,text=True,timeout=500)
print(json.dumps({'exit_code':r.returncode,'output':r.stdout[-2000:],'error':r.stderr[-2000:]}))
if r.returncode:raise SystemExit(r.returncode)
value=json.loads((work/'artifacts/startup-diagnostic.json').read_text());print(json.dumps(value))
"""
try:
 probe=call('docker','run','--rm','--network','host','--read-only','--user','0:0','--cap-drop','ALL',
  '--cap-add','CHOWN','--cap-add','DAC_OVERRIDE','--memory','128m','--memory-swap','128m','--cpus','0.5',
  '--mount','type=bind,src='+INNER+',dst='+INNER,'--mount','type=bind,src=/var/run/docker.sock,dst=/var/run/docker.sock',
  '--entrypoint','python3',inputs['runtime_image_id'],'-B','-c',inner_program,timeout=600)
 print(probe)
finally:
 assert not call('docker','ps','-q','--filter','label=io.graphato.e2e.owner')
 call('apparmor_parser','-R','-T',INNER+'/source/deployments/linux/host/graphato-server.apparmor')
 assert set(pathlib.Path('/sys/kernel/security/apparmor/profiles').read_text().splitlines())==before
'''


def main():
    attempt = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder = ROOT / 'test-results/nas-parity/followup/nas-native-startup-diagnostics' / attempt
    folder.mkdir(parents=True)
    before = begin(folder, 'fixture-startup')
    idle()
    program = 'INNER=' + repr(INNER) + '\nREMOTE=' + repr(REMOTE) + '\nATTEMPT=' + repr(attempt) + '\n' + PROGRAM
    (folder / 'program.py').write_text(program, encoding='utf-8')
    try:
        response = run_script("python3 - <<'PY'\n" + program + "\nPY\n", ROOT / '.local/nas-ssh.json', sudo=True, timeout=660)
        (folder / 'stdout.log').write_text(response.stdout, encoding='utf-8')
        (folder / 'stderr.log').write_text(response.stderr, encoding='utf-8')
        print(json.dumps({'folder': str(folder), 'exit_code': response.returncode}), flush=True)
        assert response.returncode == 0, response.stderr[-1500:]
        value = json.loads(response.stdout.splitlines()[-1])
        (folder / 'startup-diagnostic.json').write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'fixture_ready': value['ready'], 'original_tests_executed': False,
                          'error': value['error'], 'services': [c['service'] for c in value['containers']]}), flush=True)
    finally:
        finish(folder, 'fixture-startup', before)


if __name__ == '__main__':
    main()

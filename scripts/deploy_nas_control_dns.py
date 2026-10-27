"""Keep the owned control database reachable when Docker's DNS is unavailable."""

import argparse
import json
from datetime import datetime, timezone

import nas_release_vm as vm
from nas_gitea_target import idle
from nas_measurement_guard import begin, finish
from nas_ssh import ROOT

FOLDER=ROOT/'test-results/nas-parity/followup/control-dns-20261012'
PROGRAM=r'''
import hashlib,json,os,pathlib,subprocess,time
root=pathlib.Path('/volume1/docker/leroy-nas-parity');assert (root/'.leroy-owned').is_file()
work=root/'control-dns-deployment-20261012';assert work.exists()==RESUME
if not RESUME:work.mkdir(mode=0o700)
def call(args,timeout=30):
 try:r=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
 except subprocess.TimeoutExpired:raise RuntimeError('Bounded owned DNS deployment operation timed out') from None
 if r.returncode:raise RuntimeError('Bounded owned DNS deployment failed: '+str(r.returncode))
 return r.stdout.strip()
def inspect(n):return json.loads(call(['docker','inspect','leroy-nas-parity-'+n+'-1']))[0]
before=json.loads((work/'containers-before.json').read_text()) if RESUME else {n:inspect(n) for n in ('postgres','controller','runner','docker')}
if RESUME:assert all(inspect(n)['Id']==c['Id'] for n,c in before.items()),'Resume only inspected configuration staging'
assert all(c['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity' and c['State']['Running'] for c in before.values())
network='leroy-nas-parity_default';ip=before['postgres']['NetworkSettings']['Networks'][network]['IPAddress'];assert ip=='10.232.98.2'
assert before['postgres']['NetworkSettings']['Networks'][network]['IPAMConfig'] is None
assert not before['controller']['HostConfig']['ExtraHosts']
def persist(p,data):
 with p.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
 p.chmod(0o600)
override=root/'compose.override.yaml';raw=(work/'compose.override.yaml.before').read_bytes() if RESUME else override.read_bytes()
if not RESUME:
 persist(work/'compose.override.yaml.before',raw)
 persist(work/'containers-before.json',json.dumps(before).encode())
 with (work/'database-before.dump').open('xb') as f:
  subprocess.run(['docker','exec',before['postgres']['Id'],'pg_dump','-U','leroy','-d','leroy','-Fc'],check=True,stdout=f,timeout=120)
  f.flush();os.fsync(f.fileno())
 (work/'database-before.dump').chmod(0o600)
compose=['docker','compose','--project-directory',str(root)]
old_config=json.loads(call(compose+(['-f',str(root/'compose.yaml'),'-f',str(work/'compose.override.yaml.before')] if RESUME else [])+['config','--format','json']))
value=json.loads(raw)
assert 'networks' not in value['services']['postgres'] and 'extra_hosts' not in value['services']['controller']
value['services']['postgres']['networks']={'default':{'ipv4_address':ip}}
value['services']['controller']['extra_hosts']={'postgres':ip}
if RESUME:assert override.read_text()==json.dumps(value,indent=2)+'\n'
else:override.write_text(json.dumps(value,indent=2)+'\n');override.chmod(0o600)
normalized=json.loads(call(compose+['config','--format','json']))
assert normalized['services']['postgres']['networks']['default']['ipv4_address']==ip
normalized['services']['postgres']['networks']=old_config['services']['postgres']['networks']
assert normalized['services']['controller'].pop('extra_hosts')==['postgres='+ip]
assert normalized==old_config,'Only owned database addressing may change'
call(compose+['stop','--timeout','60','runner','controller','postgres'],timeout=210)
after={}
for n in ('postgres','controller','runner'):
 call(compose+['up','-d','--no-deps','--pull','never',n],timeout=120)
 deadline=time.monotonic()+120
 while time.monotonic()<deadline:
  c=inspect(n)
  if c['State']['Running'] and c['State'].get('Health',{}).get('Status','healthy')=='healthy':break
  time.sleep(2)
 else:raise TimeoutError('Owned DNS deployment health check failed')
 previous=before[n]
 assert c['Image']==previous['Image']
 assert sorted(c['Mounts'],key=lambda x:x['Destination'])==sorted(previous['Mounts'],key=lambda x:x['Destination'])
 for key in ('Cmd','Entrypoint','User','WorkingDir'):assert c['Config'][key]==previous['Config'][key]
 assert sorted(c['Config']['Env'])==sorted(previous['Config']['Env'])
 host=json.loads(json.dumps(c['HostConfig']));old_host=json.loads(json.dumps(previous['HostConfig']))
 for v in (host,old_host):
  if v.get('Binds'):v['Binds']=sorted(v['Binds'])
 if n=='controller':
  assert host['ExtraHosts']==['postgres:'+ip];host['ExtraHosts']=old_host['ExtraHosts']
 assert host==old_host,'Resources changed beyond the hosts entry'
 assert c['NetworkSettings']['Networks'][network]['IPAddress']==previous['NetworkSettings']['Networks'][network]['IPAddress']
 after[n]={'id':c['Id'],'image':c['Image'],'database_ip':ip,'parent':c['HostConfig']['CgroupParent']}
assert inspect('docker')['Id']==before['docker']['Id']
check="import socket,json;print(json.dumps({'postgres_resolved_ip':socket.gethostbyname('postgres')}))"
assert json.loads(call(['docker','exec','leroy-nas-parity-controller-1','python','-c',check]))['postgres_resolved_ip']==ip
result={'services':after,'database_hostname_unchanged':'postgres','postgres_address_reserved_in_owned_network':ip,
 'controller_resolution_uses_hosts_entry':True,'images_resources_environment_mounts_unchanged':True,
 'existing_memory_protection_preserved':True,'sources_and_tests_changed':False,'lease_deadlines_changed':False,
 'production_modified':False,'backup_sha256':hashlib.file_digest((work/'database-before.dump').open('rb'),'sha256').hexdigest()}
persist(work/'deployment-proof.json',json.dumps(result,indent=2).encode())
print(json.dumps(result))
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resume-validated-staging',action='store_true')
    args=parser.parse_args()
    assert json.loads((FOLDER/'result.json').read_text())['cases']['hosts-entry']['query_succeeded']
    idle()
    assert not vm.state()['State']['Running']
    phase='dns-recovery-'+datetime.now(timezone.utc).strftime('%H%M%S') if args.resume_validated_staging else 'dns-deployment'
    before=begin(FOLDER,phase)
    try:
        value=json.loads(vm.remote('RESUME='+repr(args.resume_validated_staging)+'\n'+PROGRAM,sudo=True,timeout=600))
        (FOLDER/'deployment-proof.json').write_text(json.dumps(value,indent=2)+'\n')
        print(json.dumps(value),flush=True)
    finally:
        finish(FOLDER,phase,before)


if __name__ == '__main__':
    main()

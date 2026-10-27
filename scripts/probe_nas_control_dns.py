"""Qualify database hostname failure and a scoped hosts entry, without modifying DB.

Two bounded containers use the actual controller image and read-only SQL. Only
their resolver is deliberately unavailable; NAS DNS and services stay unchanged.
"""

import json

import nas_release_vm as vm
from nas_gitea_target import idle
from nas_measurement_guard import begin, finish
from nas_ssh import ROOT

FOLDER = ROOT / 'test-results/nas-parity/followup/control-dns-20261012'
PROGRAM = r'''
import hashlib,json,pathlib,subprocess,time
root=pathlib.Path('/volume1/docker/leroy-nas-parity');assert (root/'.leroy-owned').is_file()
work=root/'control-dns-20261012';assert not work.exists();work.mkdir(mode=0o700)
resolver=work/'resolv.conf';resolver.write_text('nameserver 127.0.0.2\noptions timeout:1 attempts:1\n');resolver.chmod(0o644)
def call(args,timeout=15):
 try:r=subprocess.run(['docker',*args],capture_output=True,text=True,timeout=timeout)
 except subprocess.TimeoutExpired:raise RuntimeError('Bounded DNS probe timed out') from None
 if r.returncode:raise RuntimeError('Bounded DNS probe failed: '+str(r.returncode))
 return r.stdout.strip()
controller=json.loads(call(['inspect','leroy-nas-parity-controller-1']))[0]
postgres=json.loads(call(['inspect','leroy-nas-parity-postgres-1']))[0]
for c in (controller,postgres):assert c['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity' and c['State']['Running']
network='leroy-nas-parity_default';ip=postgres['NetworkSettings']['Networks'][network]['IPAddress']
assert ip=='10.232.98.2'
env=next(x for x in controller['Config']['Env'] if x.startswith('LEROY_DATABASE_URL='))
code=r"""
import json,time,socket
from sqlalchemy import text
from leroy.config import Settings
from leroy.db import connect
from urllib.parse import urlsplit
assert urlsplit(Settings.load().database_url).hostname=='postgres'
at=time.perf_counter();error=None
try:
 engine,_=connect(Settings.load().database_url)
 with engine.connect() as db:
  db.execute(text('SET TRANSACTION READ ONLY'));db.execute(text("SET LOCAL statement_timeout='3s'"))
  assert db.scalar(text('SELECT 1'))==1
 engine.dispose()
except Exception as e:error=type(e).__name__
print(json.dumps({'database_hostname_unchanged':True,'read_only':True,'query_succeeded':error is None,'error_class':error,'seconds':time.perf_counter()-at}))
"""
rows={}
for fixed in (False,True):
 name='leroy-dns-proof-'+('hosts' if fixed else 'dns')+'-20261012'
 assert subprocess.run(['docker','inspect',name],capture_output=True).returncode!=0
 args=['create','--name',name,'--label','io.leroy.control-dns=20261012','--network',network,
  '--read-only','--memory','128m','--memory-swap','128m','--cpus','0.25','--pids-limit','32',
  '--log-opt','mode=non-blocking','--log-opt','max-buffer-size=1m',
  '--mount','type=bind,src='+str(resolver)+',dst=/etc/resolv.conf,readonly','--env',env,'--entrypoint','python']
 if fixed:args+=['--add-host','postgres:'+ip]
 identity=call([*args,controller['Image'],'-B','-c',code])
 try:
  info=json.loads(call(['inspect',identity]))[0]
  assert info['Image']==controller['Image'] and info['Config']['Labels']['io.leroy.control-dns']=='20261012'
  assert next(m for m in info['Mounts'] if m['Destination']=='/etc/resolv.conf')['Source']==str(resolver)
  output=call(['start','-a',identity],timeout=25)
  result=json.loads(output)
  assert result['query_succeeded']==fixed
  if not fixed:assert result['error_class']=='OperationalError'
  state=json.loads(call(['inspect',identity]))[0]['State'];assert not state['Running'] and not state['OOMKilled']
  result.update(image=info['Image'],extra_hosts=info['HostConfig']['ExtraHosts'],container_id=identity)
  rows['hosts-entry' if fixed else 'failed-resolver']=result
 finally:
  state=json.loads(call(['inspect',identity]))[0]
  assert not state['State']['Running'],'Retain a running diagnostic for inspection'
  call(['rm',identity])
print(json.dumps({'cases':rows,'resolver_fault_scoped_to_probe_containers':True,'production_modified':False,'application_sources_or_tests_changed':False,'complete_graphato_acceptance':False}))
'''


def main():
    idle()
    assert not vm.state()['State']['Running']
    FOLDER.mkdir(exist_ok=False)
    before = begin(FOLDER,'dns-probe')
    try:
        value=json.loads(vm.remote(PROGRAM,sudo=True,timeout=120))
        (FOLDER/'result.json').write_text(json.dumps(value,indent=2)+'\n')
        print(json.dumps(value),flush=True)
    finally:
        finish(FOLDER,'dns-probe',before)


if __name__ == '__main__':
    main()

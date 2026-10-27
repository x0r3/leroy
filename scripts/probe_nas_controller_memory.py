"""Qualify API memory headroom on a separate controller and isolated database."""

import argparse
import json
import re
from datetime import datetime, timezone

import nas_release_vm as vm
from diagnose_nas_release_group import SQL_PROBE
from nas_gitea_target import idle
from nas_measurement_guard import begin, finish
from nas_ssh import ROOT

FOLDER = ROOT / 'test-results/nas-parity/followup/controller-memory-20261013'
PROGRAM = r'''
import concurrent.futures,hashlib,json,os,pathlib,subprocess,time,urllib.request,urllib.parse
root=pathlib.Path('/volume1/docker/leroy-nas-parity');assert root.resolve()==root and (root/'.leroy-owned').is_file()
suffix=('-'+ATTEMPT) if ATTEMPT else '';owner='20261013'+suffix
work=root/('controller-memory-probe-20261013'+suffix);assert not work.exists();work.mkdir(mode=0o700)
name='leroy-controller-memory-probe-20261013'+suffix;database='leroy_controller_memory_probe_20261013'+suffix.replace('-','_')
def call(args,timeout=20,payload=None):
 try:r=subprocess.run(args,input=payload,capture_output=True,text=True,timeout=timeout)
 except subprocess.TimeoutExpired:raise RuntimeError('Bounded memory qualification timed out') from None
 if r.returncode:raise RuntimeError('Bounded memory qualification failed; command output withheld')
 return r.stdout.strip()
def inspect(identity):return json.loads(call(['docker','inspect',identity]))[0]
actual=inspect('leroy-nas-parity-controller-1');pg=inspect('leroy-nas-parity-postgres-1')
assert all(c['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity' and c['State']['Running'] for c in (actual,pg))
assert not inspect('leroy-nas-release-target-vm')['State']['Running']
assert subprocess.run(['docker','inspect',name],capture_output=True,timeout=10).returncode!=0
assert not call(['docker','exec',pg['Id'],'psql','-XqAt','-U','leroy','-d','postgres','-c',"SELECT datname FROM pg_database WHERE datname='"+database+"'"])
env={k:v for item in actual['Config']['Env'] for k,_,v in [item.partition('=')]}
url=urllib.parse.urlsplit(env['LEROY_DATABASE_URL']);assert url.hostname=='postgres' and url.path=='/leroy'
env['LEROY_DATABASE_URL']=urllib.parse.urlunsplit(url._replace(path='/'+database));env['LEROY_CONFIG']='/config/leroy.toml'
envfile=work/'controller.env';envfile.write_text('\n'.join(k+'='+v for k,v in env.items() if '\n' not in v)+'\n');envfile.chmod(0o600)
assert all('\n' not in v and '\r' not in v for v in env.values())
(work/'leroy.toml').write_text('');(work/'leroy.toml').chmod(0o644)
(work/'data').mkdir(mode=0o700);os.chown(work/'data',10001,10001)
password=(root/'config/admin_password').read_text().strip()
args=['docker','create','--name',name,'--label','io.leroy.controller-memory-probe='+owner,'--network','leroy-nas-parity_default',
 '--memory','512m','--memory-swap','512m','--memory-reservation','128m','--cpus','0.25','--pids-limit','128',
 '--log-opt','mode=non-blocking','--log-opt','max-buffer-size=1m','--env-file',str(envfile),
 '--add-host','postgres:'+pg['NetworkSettings']['Networks']['leroy-nas-parity_default']['IPAddress'],
 '--mount','type=bind,src='+str(work/'leroy.toml')+',dst=/config/leroy.toml,readonly',
 '--mount','type=bind,src='+str(work/'data')+',dst=/data']
for m in actual['Mounts']:
 if m['Destination'].startswith('/run/secrets/'):
  args+=['--mount','type=bind,src='+m['Source']+',dst='+m['Destination']+',readonly']
args += [actual['Image'],'sh','-c','alembic upgrade head && uvicorn leroy.api:create_app --factory --host 0.0.0.0 --port 8088']
created=None;db_created=False;rows=[]
try:
 call(['docker','exec',pg['Id'],'psql','-XqAt','-U','leroy','-d','postgres','-c','CREATE DATABASE '+database]);db_created=True
 created=call(args);info=inspect(created)
 assert info['Image']==actual['Image'] and info['Config']['Labels']['io.leroy.controller-memory-probe']==owner
 call(['docker','start',created])
 info=inspect(created)
 assert info['State']['Running'] and info['NetworkSettings']['Networks']['leroy-nas-parity_default']['IPAddress']
 address='http://'+info['NetworkSettings']['Networks']['leroy-nas-parity_default']['IPAddress']+':8088'
 def request(path,body=None):
  data=None if body is None else json.dumps(body).encode()
  headers={'Content-Type':'application/json','X-Leroy-Request':'1'}
  opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
  with opener.open(urllib.request.Request(address+path,data=data,headers=headers),timeout=8) as response:return response.status
 deadline=time.monotonic()+120
 while time.monotonic()<deadline:
  try:
   if request('/health/ready')==200:break
  except Exception:pass
  time.sleep(1)
 else:raise RuntimeError('Separate controller failed to become ready')
 pid=inspect(created)['State']['Pid'];line=next(l for l in pathlib.Path('/proc',str(pid),'cgroup').read_text().splitlines() if l.startswith('0::'))
 cgroup=pathlib.Path('/sys/fs/cgroup'+line[3:]);assert cgroup.resolve().is_relative_to(pathlib.Path('/sys/fs/cgroup'))
 def login():
  try:return {'status':request('/api/auth/login',{'username':'admin','password':password})}
  except urllib.error.HTTPError as error:return {'status':error.code}
  except Exception as error:return {'error':type(error).__name__}
 def legacy_sql():
  try:
   result=json.loads(call(['docker','exec','-i',created,'python','-'],timeout=12,payload=LEGACY_SQL_PROBE))
   return {'succeeded':result['error'] is None,'query_error':result['error']}
  except Exception as error:return {'error':type(error).__name__}
 with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
  for round_number in range(8):
   tasks=[pool.submit(login),pool.submit(login),pool.submit(legacy_sql)]
   while not all(t.done() for t in tasks):
    rows.append({'round':round_number,'memory_current_bytes':int((cgroup/'memory.current').read_text())});time.sleep(0.1)
   outcomes=[t.result() for t in tasks]
   assert all(r.get('status') in (200,429) or r.get('succeeded') for r in outcomes),'Concurrent API/probe workload failed'
   assert any(r.get('status')==200 for r in outcomes),'Authentication was not actually exercised'
   assert request('/health/ready')==200
   rows.append({'round':round_number,'outcomes':outcomes,'memory_current_bytes':int((cgroup/'memory.current').read_text())})
 info=inspect(created);events=(cgroup/'memory.events').read_text()
 assert info['State']['Running'] and not info['State']['OOMKilled'] and info['RestartCount']==0
 assert all(int(l.split()[1])==0 for l in events.splitlines() if l.split()[0] in ('oom','oom_kill'))
 result={'controller_image':actual['Image'],'memory_limit_bytes':info['HostConfig']['Memory'],
         'peak_observed_memory_bytes':max(r['memory_current_bytes'] for r in rows),'memory_events':events,
         'rounds':8,'separate_api_and_database':True,'actual_authentication_and_old_sql_probe_workload':True,
         'controller_restarts':0,'oom_kills':0,'rows':rows,'main_controller_modified':False,
         'graphato_sources_or_tests_changed':False,'complete_nas_workload_retested':False}
finally:
 if created:
  info=inspect(created);assert info['Config']['Labels']['io.leroy.controller-memory-probe']==owner
  if info['State']['Running']:call(['docker','stop','--time','20',created],timeout=35)
  assert not inspect(created)['State']['Running'];call(['docker','rm',created])
 if db_created:
  call(['docker','exec',pg['Id'],'psql','-XqAt','-U','leroy','-d','postgres','-c','DROP DATABASE '+database])
result['probe_container_and_database_removed']=True
print(json.dumps(result))
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt',default='')
    args=parser.parse_args()
    assert not args.attempt or re.fullmatch('[a-z0-9-]{1,12}',args.attempt)
    folder=FOLDER/args.attempt if args.attempt else FOLDER
    idle()
    assert not vm.state()['State']['Running']
    folder.mkdir(exist_ok=False)
    before = begin(folder, 'controller-memory')
    try:
        value = json.loads(vm.remote('ATTEMPT='+repr(args.attempt)+'\nLEGACY_SQL_PROBE='+repr(SQL_PROBE)+'\n'+PROGRAM, sudo=True, timeout=360))
        value['at'] = datetime.now(timezone.utc).isoformat()
        (folder/'result.json').write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({k:v for k,v in value.items() if k!='rows'}))
    except Exception as error:
        (folder/'error.json').write_text(json.dumps({'error_type':type(error).__name__,'original_ci_restarted':False})+'\n',encoding='utf-8')
        raise
    finally:
        finish(folder, 'controller-memory', before)


if __name__ == '__main__':
    main()

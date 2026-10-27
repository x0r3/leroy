"""Read-only worker/SQL diagnostics inside the owned NAS test stack.

The persistent observers avoid spawning Docker clients at every sample. No
request bodies, headers, process arguments or database query text are retained.
Start only for an explicitly known Leroy run; collect after that run has ended.
"""

import base64
import gzip
import hashlib
import inspect
import json
import re

import nas_release_vm as vm


def worker_interpreter(argv):
    return (len(argv) >= 3 and re.fullmatch(rb'python(?:3(?:\.\d+)?)?', argv[0].rsplit(b'/', 1)[-1]) is not None
            and argv[1:3] == [b'-m', b'leroy.worker'])

SQL = r'''
SELECT json_build_object('at_epoch',extract(epoch from clock_timestamp()),
 'observer_pid',pg_backend_pid(),'sessions',coalesce((
 SELECT json_agg(json_build_object('pid',pid,'state',state,
 'wait_type',wait_event_type,'wait_event',wait_event,
 'transaction_age_seconds',extract(epoch from clock_timestamp()-xact_start),
 'query_age_seconds',extract(epoch from clock_timestamp()-query_start),
 'blocking_pids',pg_blocking_pids(pid),
 'operation',CASE
 WHEN lower(query) LIKE '%update%runs%' THEN 'update_run'
 WHEN lower(query) LIKE '%runs%for update%' THEN 'lock_run'
 WHEN lower(query) LIKE '%from runs%' THEN 'read_run'
 WHEN lower(query) LIKE '%select 1%' THEN 'readiness'
 ELSE 'other' END))
 FROM pg_stat_activity WHERE datname=current_database() AND usename=current_user
 AND pid<>pg_backend_pid() AND state<>'idle'),'[]'::json))
'''.strip()

PROGRAM = r'''
import json,os,pathlib,re,signal,subprocess,time
root=pathlib.Path(__file__).resolve().parent
config=json.loads((root/'config.json').read_text())
assert os.geteuid()==0 and root.parent==pathlib.Path('/volume1/docker/leroy-nas-parity')
assert (root.parent/'.leroy-owned').is_file()
stopped=False
def stop(*_):
 global stopped
 stopped=True
signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
app='leroy-worker-trace-'+config['run_id']
pg='leroy-nas-parity-postgres-1';outer='leroy-nas-parity-docker-1'
def call(args,timeout=15):
 r=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
 assert r.returncode==0,'Owned metadata operation failed; output withheld'
 return r.stdout
def inspect(name,prefix=None):return json.loads(call((prefix or ['docker'])+['inspect',name]))[0]
def write(name,value):
 p=root/name;p.write_text(json.dumps(value,indent=2)+'\n');p.chmod(0o600)
def stat(p):return p.joinpath('stat').read_text().rpartition(') ')[2].split()
def fields(p):
 return {s[0].rstrip(':'):int(s[1]) for line in p.read_text().splitlines() if len(s:=line.split())>=2 and s[1].isdigit()}
def belongs(p,cid):
 return any(line.startswith('0::') and any(part in {cid,'docker-'+cid+'.scope'} for part in pathlib.PurePosixPath(line[3:]).parts) for line in p.joinpath('cgroup').read_text().splitlines())
sql_process=None;outcome='not_started'
try:
 for name in (pg,outer):
  c=inspect(name);assert c['State']['Running'] and c['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity'
 prefix=['docker','exec',outer,'docker'];name='leroy-'+config['run_id'];worker=None
 until=min(time.time()+180,config['deadline']-900)
 while time.time()<until and not stopped:
  result=subprocess.run(prefix+['inspect',name],capture_output=True,text=True,timeout=20)
  if result.returncode==0:
   c=json.loads(result.stdout)[0]
   assert c['Config']['Labels']['io.leroy.run']==config['run_id']
   assert c['Config']['Labels']['io.leroy.runner']=='runner-nas-parity' and c['Image']==config['worker_image']
   if c['State']['Running']:worker=c;break
  time.sleep(1)
 assert worker is not None,'No running owned worker; no process state inferred'
 cid=worker['Id'];python=None
 for _ in range(30):
  for p in pathlib.Path('/proc').iterdir():
   if not p.name.isdigit():continue
   try:
    if belongs(p,cid):
     argv=p.joinpath('cmdline').read_bytes().split(b'\0')
     if worker_interpreter(argv):python=p;break
   except (OSError,ValueError):pass
  if python is not None:break
  time.sleep(1)
 assert python is not None,'Owned worker interpreter not found'
 ticks=stat(python)[19];relative=next(line[3:] for line in python.joinpath('cgroup').read_text().splitlines() if line.startswith('0::'))
 cg=pathlib.Path('/sys/fs/cgroup').joinpath(*pathlib.PurePosixPath(relative).parts[1:])
 assert cg.resolve(strict=True)==cg and '..' not in pathlib.PurePosixPath(relative).parts
 write('worker-identity.json',{'container_id':cid,'worker_image':worker['Image'],'nas_python_pid':int(python.name),
  'process_start_ticks':ticks,'cgroup_path':str(cg),
  'ancestor_memory':{str(p):{k:(p/k).read_text().strip() for k in ('memory.low','memory.min','memory.high','memory.max') if (p/k).is_file()} for p in cg.parents},
  'resources':{k:worker['HostConfig'].get(k) for k in
  ('Memory','MemorySwap','MemoryReservation','NanoCpus','CgroupParent','NetworkMode','ExtraHosts')}})
 args=['docker','exec','-i','-e','PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=3000',
  '-e','PGAPPNAME='+app,pg,'psql','-XqAt','-U','leroy','-d','leroy','-v','ON_ERROR_STOP=1']
 with (root/'sql-watch.jsonl').open('xb') as output,(root/'sql-watch-errors.log').open('xb') as errors:
  os.chmod(root/'sql-watch.jsonl',0o600);os.chmod(root/'sql-watch-errors.log',0o600)
  sql_process=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=output,stderr=errors)
  sql_process.stdin.write((config['sql']+'\n\\watch 1\n').encode());sql_process.stdin.close()
  with (root/'worker-process.jsonl').open('x') as log:
   os.chmod(root/'worker-process.jsonl',0o600);previous=time.monotonic()
   while time.time()<config['deadline']-900 and not stopped and log.tell()<32*1024**2:
    try:
     process=stat(python)
     if process[0]=='Z' or process[19]!=ticks:outcome='worker_exited';break
     assert belongs(python,cid)
     now=time.monotonic();row={'at_epoch':time.time(),'sampling_gap_seconds':now-previous,
      'process_memory_kib':{k:v for k,v in fields(python/'status').items() if k in ('VmRSS','RssAnon','RssFile','VmSwap')},'threads':[]}
     previous=now
     for task in python.joinpath('task').iterdir():
      try:
       s=stat(task);status=task.joinpath('status').read_text();ns=re.search(r'(?m)^NSpid:\s+(.+)$',status)
       wchan=task.joinpath('wchan').read_text().strip();assert re.fullmatch('[A-Za-z0-9_.+-]{1,100}',wchan)
       row['threads'].append({'nas_tid':int(task.name),'namespace_tid':int(ns[1].split()[-1]) if ns else None,
        'state':s[0],'minor_faults':int(s[7]),'major_faults':int(s[9]),'user_ticks':int(s[11]),'system_ticks':int(s[12]),
        'block_io_ticks':int(s[39]) if len(s)>39 else None,'wchan':wchan,
        'schedstat':list(map(int,task.joinpath('schedstat').read_text().split())) if task.joinpath('schedstat').is_file() else None})
      except (FileNotFoundError,ProcessLookupError):pass
     row['cgroup']={k:((cg/k).read_text().strip() if (cg/k).is_file() else None) for k in
      ('memory.current','memory.swap.current','memory.low','memory.events','memory.pressure','io.pressure','cpu.stat')}
     row['host_memory_kib']={k:v for k,v in fields(pathlib.Path('/proc/meminfo')).items() if k in ('MemAvailable','SwapFree')}
     row['host_pressure']={k:pathlib.Path('/proc/pressure',k).read_text().strip() for k in ('memory','io','cpu')}
     data=json.dumps(row,separators=(',',':'))+'\n'
     if log.tell()+len(data.encode())>32*1024**2 or (root/'sql-watch.jsonl').stat().st_size>16*1024**2:
      outcome='evidence_size_bound';break
     log.write(data);log.flush()
    except (FileNotFoundError,ProcessLookupError):outcome='worker_exited';break
    time.sleep(1)
   else:outcome='bounded_observer_end'
except Exception as error:
 outcome='observer_error:'+type(error).__name__
finally:
 # Terminate only this unique diagnostic connection. No application session
 # or repository query text is passed into the evidence stream.
 sql="SELECT json_build_object('terminated_observer_pid',pid,'terminated',pg_terminate_backend(pid)) FROM pg_stat_activity WHERE datname='leroy' AND usename='leroy' AND application_name='"+app+"'"
 try:
  output=call(['docker','exec','-e','PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=3000',pg,
   'psql','-XqAt','-U','leroy','-d','leroy','-c',sql],timeout=15)
  write('sql-observer-cleanup.json',{'rows':[json.loads(s) for s in output.splitlines() if s.strip()]})
 except Exception as error:write('sql-observer-cleanup-error.json',{'error_type':type(error).__name__})
 if sql_process is not None:
  try:sql_process.wait(timeout=10)
  except subprocess.TimeoutExpired:sql_process.terminate();sql_process.wait(timeout=5)
 write('finished.json',{'at_epoch':time.time(),'outcome':outcome,'request_or_query_text_retained':False})
'''
PROGRAM = inspect.getsource(worker_interpreter) + '\n' + PROGRAM


def directory(run_id):
    assert re.fullmatch('[a-f0-9]{32}', run_id)
    return '/volume1/docker/leroy-nas-parity/worker-control-trace-' + run_id


def start_worker_trace(folder, run_id, image, deadline):
    assert re.fullmatch('sha256:[a-f0-9]{64}', image)
    remote = directory(run_id)
    config = {'run_id': run_id, 'worker_image': image, 'deadline': deadline, 'sql': SQL}
    source_sha = hashlib.sha256(PROGRAM.encode()).hexdigest()
    program = 'ROOT=' + repr(remote) + '\nSOURCE=' + repr(PROGRAM) + '\nCONFIG=' + repr(config) + '\n' + r'''
import hashlib,json,os,pathlib,subprocess,time
assert os.geteuid()==0
root=pathlib.Path(ROOT);assert not root.exists() and (root.parent/'.leroy-owned').is_file()
assert time.time()+300<CONFIG['deadline']<=time.time()+10*3600
root.mkdir(mode=0o700)
for name,data in [('observer.py',SOURCE),('config.json',json.dumps(CONFIG))]:
 p=root/name;p.write_text(data);p.chmod(0o600)
with (root/'observer.log').open('xb') as log:
 process=subprocess.Popen(['/usr/bin/python3','-B',str(root/'observer.py')],stdin=subprocess.DEVNULL,
  stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
identity={'directory':str(root),'pid':process.pid,
 'start_ticks':pathlib.Path('/proc',str(process.pid),'stat').read_text().rpartition(') ')[2].split()[19],
 'source_sha256':hashlib.sha256(SOURCE.encode()).hexdigest(),'run_id':CONFIG['run_id']}
(root/'identity.json').write_text(json.dumps(identity));(root/'identity.json').chmod(0o600)
print(json.dumps(identity))
'''
    proof = json.loads(vm.remote(program, sudo=True, timeout=45))
    assert proof['source_sha256'] == source_sha
    (folder / 'worker-control-trace.json').write_text(json.dumps(proof, indent=2) + '\n')
    return proof


def collect_worker_trace(folder):
    expected = json.loads((folder / 'worker-control-trace.json').read_text())
    program = 'EXPECTED=' + repr(expected) + '\n' + r'''
import base64,gzip,hashlib,json,os,pathlib,signal,time
root=pathlib.Path(EXPECTED['directory']);assert root.resolve()==root and not root.is_symlink()
assert root.parent==pathlib.Path('/volume1/docker/leroy-nas-parity')
assert json.loads((root/'identity.json').read_text())==EXPECTED
assert hashlib.sha256((root/'observer.py').read_bytes()).hexdigest()==EXPECTED['source_sha256']
p=pathlib.Path('/proc',str(EXPECTED['pid']))
if p.exists() and p.joinpath('stat').read_text().rpartition(') ')[2].split()[0]!='Z':
 assert p.joinpath('stat').read_text().rpartition(') ')[2].split()[19]==EXPECTED['start_ticks']
 assert p.joinpath('cmdline').read_bytes().split(b'\0')[:-1]==[b'/usr/bin/python3',b'-B',str(root/'observer.py').encode()]
 os.kill(EXPECTED['pid'],signal.SIGTERM)
for _ in range(80):
 if (root/'finished.json').exists():break
 time.sleep(.5)
assert (root/'finished.json').exists(),'Retain the bounded observer; collect only after it has flushed'
rows={}
for name in ('finished.json','worker-identity.json','worker-process.jsonl','sql-watch.jsonl','sql-observer-cleanup.json','sql-observer-cleanup-error.json'):
 p=root/name
 if not p.exists():continue
 assert not p.is_symlink() and p.stat().st_size<=32*1024**2
 data=p.read_bytes();rows[name]={'sha256':hashlib.sha256(data).hexdigest(),'gzip_base64':base64.b64encode(gzip.compress(data)).decode()}
print(json.dumps(rows))
'''
    values = json.loads(vm.remote(program, sudo=True, timeout=70))
    output = folder / 'worker-control-trace'
    output.mkdir()
    for name, row in values.items():
        assert re.fullmatch(r'[a-z-]+\.(json|jsonl)', name)
        data = gzip.decompress(base64.b64decode(row['gzip_base64']))
        assert hashlib.sha256(data).hexdigest() == row['sha256']
        (output / name).write_bytes(data)
    return json.loads((output / 'finished.json').read_text())

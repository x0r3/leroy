"""Compare incoming-only and bidirectional metadata capture on an owned NAS bridge."""

import hashlib
import json
import subprocess
from datetime import datetime, timezone

from nas_gitea_target import idle
from nas_measurement_guard import begin, finish
from nas_ssh import ROOT, run_script, upload_file
from prepare_nas_native_soak import INNER, REMOTE

PROGRAM = r'''
import hashlib,json,pathlib,subprocess,time
assert pathlib.Path('/volume1/docker/leroy-nas-parity/.leroy-owned').is_file()
prefix=['docker','exec','leroy-nas-parity-docker-1']
def call(*args,timeout=60):return subprocess.check_output([*prefix,*args],text=True,timeout=timeout).strip()
stage=pathlib.Path(REMOTE);inputs=json.loads((stage/'inputs.json').read_text())
transfer=pathlib.Path(TRANSFER);assert transfer.resolve().is_relative_to(stage.resolve())
ORIGINAL=(transfer/'original.py').read_bytes();CORRECTED=(transfer/'corrected.py').read_bytes()
assert hashlib.sha256(ORIGINAL).hexdigest()==ORIGINAL_SHA and hashlib.sha256(CORRECTED).hexdigest()==CORRECTED_SHA
assert hashlib.sha256(ORIGINAL).hexdigest()==inputs['observer_sha256']
assert ORIGINAL.count(b'socket.htons(0x0800)')==1
variants={'original':ORIGINAL,'protocol-only':ORIGINAL.replace(b'socket.htons(0x0800)',b'socket.htons(0x0003)'), 'corrected':CORRECTED}
target=stage/'transport-diagnostics'/ATTEMPT
assert not target.exists();target.mkdir(parents=True,mode=0o700)
for name,data in variants.items():
 (target/(name+'.py')).write_bytes(data);(target/name).mkdir(mode=0o700)
inner=INNER+'/transport-diagnostics/'+ATTEMPT
call('test','!','-e',inner);call('mkdir','-p',INNER+'/transport-diagnostics')
subprocess.run(['docker','cp',str(target),'leroy-nas-parity-docker-1:'+inner],check=True,capture_output=True,timeout=60)
assert not call('docker','ps','-q','--filter','label=io.graphato.e2e.owner')
assert not call('docker','ps','-aq','--filter','label=io.leroy.transport-probe')
profile=stage/'source/deployments/linux/host/graphato-server.apparmor'
assert hashlib.sha256(profile.read_bytes()).hexdigest()==inputs['apparmor_profile_sha256']
before=set(pathlib.Path('/sys/kernel/security/apparmor/profiles').read_text().splitlines())
assert not any(p.startswith('graphato-server ') for p in before)
call('apparmor_parser','-a','-T',INNER+'/source/deployments/linux/host/graphato-server.apparmor')
assert set(pathlib.Path('/sys/kernel/security/apparmor/profiles').read_text().splitlines())==before|{'graphato-server (enforce)'}
network='leroy-transport-'+ATTEMPT.lower();containers=[]
server_program=r"""
from http.server import HTTPServer,BaseHTTPRequestHandler
import json
class Handler(BaseHTTPRequestHandler):
 protocol_version='HTTP/1.1'
 def log_message(self,*args):pass
 def do_POST(self):
  command=json.loads(self.rfile.read(int(self.headers['Content-Length'])))['command']
  status=429 if command=='transportLimitedProbe' else 200
  body=json.dumps({'probe':True,'padding':'x'*8192}).encode()
  self.send_response(status);self.send_header('Content-Length',str(len(body)))
  if status==429:self.send_header('Retry-After','1')
  self.end_headers();self.wfile.write(body)
 def do_GET(self):
  body=b'{}';self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
HTTPServer(('0.0.0.0',8042),Handler).serve_forever()
"""
client_program=r"""
import http.client,json
c=http.client.HTTPConnection('passive-server',8042,timeout=10)
statuses=[]
for command in ['transportProbe','transportLimitedProbe','transportProbe','transportProbe']:
 c.request('POST','/api/v1/commands',json.dumps({'command':command,'args':{'private':'PRIVATE_TEST_MARKER'}}),{'Authorization':'Bearer PRIVATE_TEST_MARKER','Content-Type':'application/json'})
 r=c.getresponse();statuses.append(r.status);r.read()
c.request('GET','/api/v1/health');r=c.getresponse();statuses.append(r.status);r.read();c.close()
assert statuses==[200,429,200,200,200];print(json.dumps({'statuses':statuses,'requests':5}))
"""
result={'scope':'Transport probe only; no Graphato tests or application commands executed','variants':{},'runtime_image_id':inputs['runtime_image_id']}
try:
 call('docker','network','create','--label','io.leroy.transport-probe='+ATTEMPT,network)
 server=call('docker','run','-d','--name',network+'-server','--label','io.leroy.transport-probe='+ATTEMPT,
  '--network',network,'--network-alias','passive-server','--read-only','--user','1000:1000','--cap-drop','ALL',
  '--security-opt','apparmor=graphato-server','--memory','128m','--memory-swap','128m','--cpus','0.25',
  '--entrypoint','python3',inputs['runtime_image_id'],'-B','-u','-c',server_program)
 containers.append(server)
 state=json.loads(call('docker','inspect',server))[0];assert state['State']['Running'] and state['Image']==inputs['runtime_image_id']
 for name in variants:
  observer=call('docker','run','-d','--name',network+'-'+name,'--label','io.leroy.transport-probe='+ATTEMPT,
   '--network','none','--pid','host','--read-only','--user','0:0','--cap-drop','ALL','--cap-add','NET_RAW',
   '--cap-add','SYS_ADMIN','--cap-add','SYS_PTRACE','--cap-add','DAC_OVERRIDE',
   '--security-opt','apparmor=graphato-server','--security-opt','no-new-privileges:true',
   '--memory','64m','--memory-swap','64m','--cpus','0.1','--pids-limit','32',
   '--mount','type=bind,src='+inner+'/'+name+'.py,dst=/observe.py,readonly',
   '--mount','type=bind,src='+inner+'/'+name+',dst=/metadata',
   '--entrypoint','python3',inputs['runtime_image_id'],'-B','/observe.py','--output','/metadata/http-metadata.jsonl',
   '--network-namespace-pid',str(state['State']['Pid']))
  containers.append(observer);result['variants'][name]={'container_id':observer,'program_sha256':hashlib.sha256(variants[name]).hexdigest()}
  deadline=time.monotonic()+45
  while 'Passive metadata observer ready' not in call('docker','logs',observer):
   assert json.loads(call('docker','inspect',observer))[0]['State']['Running'] and time.monotonic()<deadline
   time.sleep(0.5)
 client=call('docker','run','--rm','--network',network,'--read-only','--user','1000:1000','--cap-drop','ALL',
  '--memory','64m','--memory-swap','64m','--cpus','0.25','--entrypoint','python3',inputs['runtime_image_id'],'-B','-c',client_program)
 result['client']=json.loads(client)
 time.sleep(1)
 for name,value in result['variants'].items():
  observer=value['container_id'];call('docker','stop','--time','5',observer)
  assert json.loads(call('docker','inspect',observer))[0]['State']['ExitCode']==0
  raw=call('cat',inner+'/'+name+'/http-metadata.jsonl');assert 'PRIVATE_TEST_MARKER' not in raw
  rows=[json.loads(l) for l in raw.splitlines()];value['rows']=rows
  value['requests']=len([r for r in rows if r['kind']=='request'])
  value['responses']=len([r for r in rows if r['kind']=='response'])
  value['http_429_responses']=len([r for r in rows if r['kind']=='response' and r['status']==429])
  value['parser_counts']=rows[-1]['counts']
 assert result['variants']['original']['requests']==5 and result['variants']['original']['responses']==0
 for name in ['protocol-only','corrected']:
  assert result['variants'][name]['requests']==5 and result['variants'][name]['responses']==5
  assert result['variants'][name]['http_429_responses']==1
  assert result['variants'][name]['parser_counts'].get('kernel_packets_dropped')==0
 result['incoming_only_error_reproduced']=True;result['protocol_only_correction_verified']=True
 result['credentials_not_emitted']=True
finally:
 for identity in reversed(containers):
  c=json.loads(call('docker','inspect',identity))[0]
  assert c['Config']['Labels']['io.leroy.transport-probe']==ATTEMPT
  call('docker','rm','-f',identity)
 if subprocess.run([*prefix,'docker','network','inspect',network],capture_output=True,timeout=20).returncode==0:
  n=json.loads(call('docker','network','inspect',network))[0]
  assert n['Labels']['io.leroy.transport-probe']==ATTEMPT and not n['Containers'];call('docker','network','rm',network)
 call('apparmor_parser','-R','-T',INNER+'/source/deployments/linux/host/graphato-server.apparmor')
 assert set(pathlib.Path('/sys/kernel/security/apparmor/profiles').read_text().splitlines())==before
print(json.dumps(result))
'''


def main():
    attempt = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder = ROOT / 'test-results/nas-parity/followup/nas-passive-transport' / attempt
    folder.mkdir(parents=True)
    before = begin(folder, 'passive-transport')
    idle()
    original = subprocess.check_output(['git', 'show',
                                        '102691952df6f14a39f70682ad8d8c282c138ace:scripts/diagnostics/nas-passive-http.py'], cwd=ROOT)
    corrected = (ROOT / 'scripts/diagnostics/nas-passive-http.py').read_bytes()
    assert hashlib.sha256(original).hexdigest() != hashlib.sha256(corrected).hexdigest()
    program = 'INNER=' + repr(INNER) + '\nREMOTE=' + repr(REMOTE) + '\nATTEMPT=' + repr(attempt) + '\n'
    transfer = REMOTE + '/transport-upload/' + attempt
    program += 'TRANSFER=' + repr(transfer) + '\nORIGINAL_SHA=' + repr(hashlib.sha256(original).hexdigest()) + '\n'
    program += 'CORRECTED_SHA=' + repr(hashlib.sha256(corrected).hexdigest()) + '\n' + PROGRAM
    (folder / 'program.py').write_text(program, encoding='utf-8')
    try:
        create = "import pathlib;assert pathlib.Path('/volume1/docker/leroy-nas-parity/.leroy-owned').is_file();p=pathlib.Path(" + repr(transfer) + ");p.mkdir(parents=True,mode=0o700)"
        created = run_script("python3 - <<'PY'\n" + create + "\nPY\n", ROOT / '.local/nas-ssh.json', timeout=30)
        assert created.returncode == 0, created.stderr[-1000:]
        for name, data in [('original.py', original), ('corrected.py', corrected)]:
            path = folder / name
            path.write_bytes(data)
            upload_file(path, transfer + '/' + name, ROOT / '.local/nas-ssh.json', timeout=60)
        response = run_script("python3 - <<'PY'\n" + program + "\nPY\n", ROOT / '.local/nas-ssh.json', sudo=True, timeout=420)
        (folder / 'stdout.log').write_text(response.stdout, encoding='utf-8')
        (folder / 'stderr.log').write_text(response.stderr, encoding='utf-8')
        print(json.dumps({'folder': str(folder), 'exit_code': response.returncode}), flush=True)
        assert response.returncode == 0, response.stderr[-1500:]
        result = json.loads(response.stdout.splitlines()[-1])
        (folder / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({name: {k: v[k] for k in ('requests', 'responses', 'http_429_responses')}
                          for name, v in result['variants'].items()}, indent=2), flush=True)
    finally:
        finish(folder, 'passive-transport', before)


if __name__ == '__main__':
    main()

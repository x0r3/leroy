"""Read public endpoint reachability in the future native NAS execution context.

No credentials, request bodies, application writes or firewall changes are used.
The temporary probe has no Docker socket or production filesystem mounts.
"""

import json
from datetime import datetime, timezone

from nas_ssh import ROOT, run_script

PROBE = r'''
import json,socket,urllib.error,urllib.request
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args):return None
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
rows=[]
for name,url in [('git','http://192.168.178.97:3000/api/v1/version'),
                 ('registry','http://192.168.178.97:5005/v2/'),
                 ('paperless','http://192.168.178.97:8010/api/')]:
 try:
  with opener.open(urllib.request.Request(url,method='GET'),timeout=10) as response:status=response.status
  rows.append({'service':name,'url':url,'http_status':status,'reachable':True})
 except urllib.error.HTTPError as error:
  rows.append({'service':name,'url':url,'http_status':error.code,'reachable':True})
 except (OSError,urllib.error.URLError) as error:
  rows.append({'service':name,'url':url,'reachable':False,'error_type':type(error).__name__})
ssh=[]
for name,host,port in [('graphato','87.106.133.233',22),('hub','213.165.73.233',22),('music','192.168.178.84',8022)]:
 try:
  with socket.create_connection((host,port),timeout=10):pass
  ssh.append({'target':name,'host':host,'port':port,'tcp_reachable':True,'authenticated':False})
 except OSError as error:
  ssh.append({'target':name,'host':host,'port':port,'tcp_reachable':False,'error_type':type(error).__name__,'authenticated':False})
print(json.dumps({'http':rows,'ssh':ssh,'application_response_bodies_exported':False,'credentials_supplied':False}))
'''

PROGRAM = r'''
import json,pathlib,subprocess,uuid
root=pathlib.Path('/volume1/docker/leroy-nas-parity')
assert (root/'.leroy-owned').is_file()
info=json.loads(subprocess.check_output(['docker','inspect','leroy-nas-parity-controller-1']))[0]
assert info['Config']['Labels']['com.docker.compose.project']=='leroy-nas-parity'
network='home-lab-stack_default'
net=json.loads(subprocess.check_output(['docker','network','inspect',network]))[0]
assert net['Name']==network and net['Driver']=='bridge'
name='leroy-production-route-probe-'+uuid.uuid4().hex[:12]
args=['docker','run','--rm','--name',name,'--label','io.leroy.production-review=routes',
      '--network',network,'--read-only','--memory','128m','--memory-swap','128m','--cpus','.25',
      '--pids-limit','64','--cap-drop','ALL','--security-opt','no-new-privileges',
      '--user','65534','--entrypoint','python',info['Image'],'-B','-c',PROBE]
try:
 result=subprocess.run(args,capture_output=True,text=True,timeout=100)
 assert result.returncode==0,'Temporary metadata probe failed: '+str(result.returncode)
 value=json.loads(result.stdout)
finally:
 # Exact unique probe name; no native application container is stopped.
 subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=20)
daemon=json.loads(subprocess.check_output(['docker','info','--format','{{json .RegistryConfig}}']))
value.update({'probe_image_id':info['Image'],'native_network':network,'native_docker_daemon_context':True,
              'probe_docker_socket_mounted':False,'probe_production_filesystems_mounted':False,
              'insecure_registry_cidrs':daemon.get('InsecureRegistryCIDRs',[]),
              'registry_index_security':{name:row['Secure'] for name,row in daemon.get('IndexConfigs',{}).items()},
              'test_isolation_modified':False,'production_application_modified':False,
              'actual_credential_permissions_validated':False,'production_replacement_ready':False})
print(json.dumps(value))
'''


def main():
    folder = ROOT / 'test-results/nas-parity/followup/cutover-preparation'
    destination = folder / 'native-context-public-route-probe.json'
    assert not destination.exists(), 'Retain the observation; use an explicitly distinct probe for a new observation'
    program = 'PROBE=' + repr(PROBE) + '\n' + PROGRAM
    compile(program, 'native-context read-only route probe', 'exec')
    result = run_script("python3 - <<'PY'\n" + program + "\nPY\n", ROOT / '.local/nas-ssh.json',
                        sudo=True, timeout=150)
    assert result.returncode == 0, 'Metadata probe failed; no credentials or response bodies exported'
    record = json.loads(result.stdout)
    record['at'] = datetime.now(timezone.utc).isoformat()
    record['scope'] = 'Public HTTP/TCP reachability in the native Docker network; no credential or deployment acceptance'
    destination.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({'http': record['http'], 'ssh': record['ssh'], 'production_replacement_ready': False}), flush=True)


if __name__ == '__main__':
    main()

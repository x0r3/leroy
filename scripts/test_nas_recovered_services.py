"""Probe owned services, the recovered test tunnel and network rejection rules."""

from nas_diagnostic import execute

PROGRAM = r"""
import json,os,pathlib,socket,subprocess,urllib.request
from leroy.actions import ssh_args
from leroy.ssh_session import shared_ssh
http={}
for url in ['http://controller:8088/health/ready','http://registry:5000/v2/','http://gitea:3000/api/v1/version']:
 with urllib.request.urlopen(url,timeout=10) as response:
  assert response.status==200
  http[url]=response.status
blocked=[]
for host,port in [('192.168.178.97',9000),('87.106.133.233',22)]:
 try:
  with socket.create_connection((host,port),timeout=3):pass
 except OSError:
  blocked.append({'host':host,'port':port})
 else:raise AssertionError('A protected network endpoint became reachable')
args=ssh_args('graphato-vm','root',12225,os.environ['DEPLOY_KEY'],os.environ['KNOWN_HOSTS'])
with shared_ssh(args) as transport:
 result=subprocess.run([*transport,'status'],capture_output=True,text=True,timeout=15,check=True)
 status=json.loads(result.stdout)
 assert status['commit']=='48b741264f3b8353400649f6b05abf6a9c129233'
 assert status['postdeployProtocol']==2
report={'http':http,'blocked_tcp_endpoints':blocked,'test_tunnel_recovered':True,'vm_commit':status['commit'],'read_only':True}
pathlib.Path('services.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
"""


if __name__ == "__main__":
    execute("nas-stack-services", PROGRAM, secrets=["graphato-deploy"], artifacts=["services.json"])

"""Prepare the isolated Hub network and capture actual target runtime state."""

import argparse
import json

from nas_ssh import ROOT
from prepare_nas_vm import guest

RESULTS = ROOT / "test-results/nas-parity/aligned"


def prepare():
    print(
        guest("""sudo sh -eu <<'SH'
test -f /var/lib/leroy-vm/ready
test "$(systemd-detect-virt)" = kvm
docker network inspect nikicas-hub_default >/dev/null 2>&1 || docker network create --subnet 172.31.91.0/24 --label com.docker.compose.project=nikicas-hub --label com.docker.compose.network=default nikicas-hub_default
iptables -N LEROY-HUB-TEST 2>/dev/null || true
iptables -F LEROY-HUB-TEST
iptables -A LEROY-HUB-TEST -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
iptables -A LEROY-HUB-TEST -d 172.31.91.0/24 -j RETURN
iptables -A LEROY-HUB-TEST -d 172.31.90.0/24 -j RETURN
iptables -A LEROY-HUB-TEST -j REJECT
iptables -C DOCKER-USER -s 172.31.91.0/24 -j LEROY-HUB-TEST 2>/dev/null || iptables -I DOCKER-USER 1 -s 172.31.91.0/24 -j LEROY-HUB-TEST
echo 'Hub test containers cannot contact public services, including public ACME.'
SH""")
    )


def capture(engine, stage):
    program = """import hashlib,json,pathlib,pwd,stat,subprocess
root=pathlib.Path('/opt/nikicas-hub')
paths=['data','react-app/server/public_gallery','react-app/server/private_gallery','letsencrypt/acme.json']
files={}
for name in paths:
 path=root/name;info=path.stat()
 files[name]={'uid':info.st_uid,'gid':info.st_gid,'mode':oct(stat.S_IMODE(info.st_mode))}
user=pwd.getpwnam('nikicas-hub-deploy')
result={'deploy_user':{'uid':user.pw_uid,'gid':user.pw_gid},'paths':files}
if STAGE=='deploy':
 identities=subprocess.check_output(['docker','ps','-aq','--filter','label=com.docker.compose.project=nikicas-hub'],text=True).split()
 containers=json.loads(subprocess.check_output(['docker','inspect',*identities],text=True)) if identities else []
 result['containers']=[]
 for c in containers:
  state=c['State'];service=c['Config']['Labels']['com.docker.compose.service']
  row={'service':service,'image':c['Image'],'status':state['Status'],'running':state['Running'],'restart_count':c['RestartCount'],'health':state.get('Health',{}).get('Status'),'user':c['Config']['User']}
  if service=='app':
   check=subprocess.run(['docker','exec',c['Id'],'wget','-q','-O','/dev/null','http://127.0.0.1:8080'],capture_output=True,text=True)
   row['http_probe_exit_code']=check.returncode
   row['http_probe_error']=check.stderr[-500:]
   log=subprocess.run(['docker','logs','--tail','30',c['Id']],capture_output=True,text=True)
   row['database_open_failure_observed']='SQLITE_CANTOPEN' in log.stdout+log.stderr
   probe=subprocess.run(['docker','run','--rm','--network','none','--read-only','--mount','type=bind,source=/opt/nikicas-hub/data,target=/data','--entrypoint','node',c['Image'],'-e',"const fs=require('fs');let writable=true;try{fs.accessSync('/data',fs.constants.W_OK)}catch{writable=false}console.log(JSON.stringify({uid:process.getuid(),gid:process.getgid(),data_writable:writable}))"],capture_output=True,text=True,check=True)
   row['runtime_permissions']=json.loads(probe.stdout)
  result['containers'].append(row)
 result['containers'].sort(key=lambda c:c['service'])
 result['compose_sha256']=hashlib.sha256((root/'prod/docker-compose.yml').read_bytes()).hexdigest()
print(json.dumps(result))
"""
    result = json.loads(guest("sudo python3 -", "STAGE=" + repr(stage) + "\n" + program))
    folder = RESULTS / ("nikicas-hub-bootstrap-host" if stage == "bootstrap" else "nikicas-hub-deploy")
    (folder / (engine + "-target-state.json")).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["prepare", "capture"])
    parser.add_argument("engine", choices=["jenkins", "leroy"])
    parser.add_argument("--stage", choices=["bootstrap", "deploy"], default="bootstrap")
    args = parser.parse_args()
    if args.phase == "prepare":
        prepare()
    else:
        capture(args.engine, args.stage)


if __name__ == "__main__":
    main()

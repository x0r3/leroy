"""Exercise the NAS controller's distributed worker before the unchanged CI pair."""

import hashlib
import json
import subprocess

from nas_diagnostic import execute
from nas_ssh import ROOT
from setup_nas_linux_pool import COMMIT, EVIDENCE, LOCAL, PARENT, docker


def main():
    pool = json.loads((EVIDENCE / "pool.json").read_text())
    assert pool["candidate"] == COMMIT and pool["parent"] == PARENT
    info = json.loads(docker("inspect", PARENT, text=True).stdout)[0]
    assert info["Id"] == pool["parent_id"] and info["State"]["Running"]
    rules = docker("exec", PARENT, "iptables", "-S", "LEROY-POOL-EGRESS", text=True).stdout
    assert "192.168.178.97/32" in rules and "--dport 8088 -j RETURN" in rules
    assert "192.168.0.0/16 -j REJECT" in rules
    jenkinsfile = subprocess.check_output(["git", "-C", str(ROOT / ".sources/antares-capture-validation"), "show", COMMIT + ":Jenkinsfile"])
    values = {"POOL": pool, "JENKINSFILE_SHA": hashlib.sha256(jenkinsfile).hexdigest()}
    program = "\n".join(key + "=" + repr(value) for key, value in values.items()) + "\n" + r'''
import hashlib,json,os,pathlib,socket,subprocess,urllib.request
worker=json.loads(subprocess.check_output(['docker','inspect',os.environ['HOSTNAME']],text=True))[0]
assert worker['Config']['Labels']['io.leroy.runner']=='runner-nas-linux-pool'
assert worker['HostConfig']['Memory']==4*1024**3 and worker['HostConfig']['NanoCpus']==6_000_000_000
assert 'LEROY_CONTROLLER='+POOL['controller'] in worker['Config']['Env']
assert hashlib.sha256(pathlib.Path('/usr/local/bin/docker').read_bytes()).hexdigest()==POOL['policy_sha256']
assert not pathlib.Path('/sources').is_file()
head=subprocess.check_output(['git','ls-remote',POOL['source'],'refs/heads/master'],text=True,timeout=30).split()[0]
assert head==POOL['candidate']
with urllib.request.urlopen(POOL['source']+'/HEAD',timeout=15) as response:
 assert response.read().decode().strip()=='ref: refs/heads/master'
repo=pathlib.Path('/sources/gitea-admin/antares-candidate-'+head[:12]+'.git')
data=subprocess.check_output(['git','-c','safe.directory='+str(repo),'--git-dir',str(repo),'show',head+':Jenkinsfile'],timeout=15)
assert hashlib.sha256(data).hexdigest()==JENKINSFILE_SHA
with urllib.request.urlopen(POOL['controller']+'/health/ready',timeout=15) as response:
 assert response.status==200
blocked=[]
for port in [22,9000,9443]:
 try:
  connection=socket.create_connection(('192.168.178.97',port),timeout=2);connection.close()
 except OSError:blocked.append(port)
assert blocked==[22,9000,9443]
jenkins=json.loads(subprocess.check_output(['docker','inspect','jenkins-parity'],text=True,timeout=15))[0]
assert jenkins['Id']==POOL['jenkins_id'] and not jenkins['State']['Running']
report={'candidate':head,'controller_reachable':True,'runner':'runner-nas-linux-pool',
 'job_memory_bytes':worker['HostConfig']['Memory'],'job_cpus':6,'job_image':worker['Image'],
 'blocked_nas_ports':blocked,'jenkins_stopped':True,'jenkinsfile_sha256':JENKINSFILE_SHA,
 'production_modified':False,'full_ci_acceptance':False,'passed':True}
pathlib.Path('pool-preflight.json').write_text(json.dumps(report))
print(json.dumps(report),flush=True)
'''
    folder, run = execute("antares-linux-pool-preflight-" + COMMIT[:12] + "-v2", program,
                          timeout=120, artifacts=["pool-preflight.json"], profile=pool["profile"])
    record = json.loads((folder / "leroy-artifacts/probe/pool-preflight.json").read_text())
    record.update(run=run["id"], parent_id=pool["parent_id"], firewall_rules=rules,
                  worker_configuration_sha256=hashlib.sha256((LOCAL / "runner.toml").read_bytes()).hexdigest())
    (EVIDENCE / "preflight.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record), flush=True)


if __name__ == "__main__":
    main()

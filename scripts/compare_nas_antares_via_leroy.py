"""Run the unchanged Antares Jenkins gates through the isolated worker transport."""

import argparse
import json
import re
import subprocess

from collect_nas_jenkins_evidence import PROGRAM as COLLECT
from nas_diagnostic import execute
from nas_followup_support import production_jobs, wait_production_build, wait_production_jobs
from nas_ssh import ROOT
from watch_nas_graphato_via_leroy import JENKINS_ID, in_container

PROGRAM = r"""
import json,os,pathlib,subprocess,time
output=pathlib.Path('evidence');output.mkdir()
def docker(*args,timeout=60):return subprocess.check_output(['docker',*args],text=True,timeout=timeout)
info=json.loads(docker('inspect','jenkins-parity'))[0]
assert info['Id']==EXPECTED_ID and not info['State']['Running']
worker=json.loads(docker('inspect',os.environ['HOSTNAME']))[0]
assert worker['Config']['Labels']['io.leroy.run']
assert worker['HostConfig']['Memory']==JOB_MEMORY and worker['HostConfig']['NanoCpus']==JOB_CPUS*1_000_000_000
assert os.environ['NODE_OPTIONS']=='--max-old-space-size=2048'
assert subprocess.check_output(['git','ls-remote',SOURCE,'refs/heads/master'],text=True,timeout=30).split()[0]==COMMIT
before={key:info['HostConfig'][key] for key in ('Memory','MemorySwap','NanoCpus')}
assert before=={'Memory':2*1024**3,'MemorySwap':4*1024**3,'NanoCpus':2_000_000_000}
swap=worker['HostConfig']['MemorySwap']
assert swap==-1 or swap>=worker['HostConfig']['Memory']
docker('update','--memory',str(JOB_MEMORY),'--memory-swap',str(swap),'--cpus',str(JOB_CPUS),'jenkins-parity')
resources=json.loads(docker('inspect','jenkins-parity'))[0]['HostConfig']
assert all(resources[key]==worker['HostConfig'][key] for key in ('Memory','MemorySwap','NanoCpus'))
docker('start','jenkins-parity')
def jenkins(script):
 return json.loads(subprocess.check_output(['docker','exec','-i','jenkins-parity','python3','-'],input=AUTH+'\n'+script,text=True,timeout=90))
for attempt in range(48):
 try:
  state=jenkins("print(request('/api/json?tree=jobs[name,nextBuildNumber,lastBuild[building]]').decode())")
  break
 except subprocess.CalledProcessError:
  if attempt==47:raise
  time.sleep(5)
assert not any((job.get('lastBuild') or {}).get('building') for job in state['jobs'])
assert not jenkins("print(request('/queue/api/json?tree=items[id]').decode())")['items']
toolchains={engine:{tool:subprocess.check_output([*prefix,tool,'--version'],text=True,timeout=30).strip() for tool in ('node','npm','git','docker')} for engine,prefix in (('jenkins',['docker','exec','jenkins-parity']),('leroy',[]))}
for engine,prefix in (('jenkins',['docker','exec','jenkins-parity']),('leroy',[])):
 for plugin in ('compose','buildx'):
  result=subprocess.run([*prefix,'docker',plugin,'version'],text=True,capture_output=True,timeout=30)
  toolchains[engine][plugin]=result.stdout.strip() if result.returncode==0 else 'unavailable'
assert toolchains['jenkins']==toolchains['leroy'],toolchains
images={name:json.loads(docker('image','inspect',name))[0]['Id'] for name in ('postgres:18.4-alpine3.24','mcr.microsoft.com/playwright:v1.61.1-noble')}
groovy='''import jenkins.model.Jenkins
import hudson.slaves.EnvironmentVariablesNodeProperty
def instance=Jenkins.get()
assert !instance.items.any { it.lastBuild?.building }
def property=instance.globalNodeProperties.get(EnvironmentVariablesNodeProperty)
assert property!=null && property.envVars.get('NODE_OPTIONS')==null
property.envVars.put('NODE_OPTIONS','--max-old-space-size=2048')
instance.save()
println('Antares test budget applied')
'''
message=jenkins('print(json.dumps(request("/scriptText",urllib.parse.urlencode({"script":'+repr(groovy)+'}).encode()).decode()))')
assert message.strip()=='Antares test budget applied'
original=jenkins("print(json.dumps(request('/job/antares-ci/config.xml').decode()))")
(output/'jenkins-before.xml').write_text(original)
import xml.etree.ElementTree as ET
xml=ET.fromstring(original)
assert xml.findtext('.//scriptPath')=='Jenkinsfile'
assert xml.find('.//hudson.plugins.git.UserRemoteConfig/credentialsId') is None
xml.find('.//hudson.plugins.git.UserRemoteConfig/url').text=SOURCE
candidate=ET.tostring(xml,encoding='unicode');(output/'jenkins-candidate.xml').write_text(candidate)
number=next(job['nextBuildNumber'] for job in state['jobs'] if job['name']=='antares-ci')
request_script="headers['Content-Type']='application/xml'\nrequest('/job/antares-ci/config.xml',"+repr(candidate)+".encode())\nheaders['Content-Type']='application/x-www-form-urlencoded'\nrequest('/job/antares-ci/build',b'')\nprint(json.dumps({'number':"+str(number)+"}))"
jenkins(request_script)
identity={'candidate':COMMIT,'number':number,'jenkins_container_id':EXPECTED_ID,
 'jenkins_memory':resources['Memory'],'jenkins_cpus':resources['NanoCpus']/1e9,
 'leroy_memory':worker['HostConfig']['Memory'],'leroy_cpus':worker['HostConfig']['NanoCpus']/1e9,
 'memory_swap_both':swap,'node_options':os.environ['NODE_OPTIONS'],'source':SOURCE,
 'toolchains':toolchains,'shared_service_images':images,'job_images':{'jenkins':info['Image'],'leroy':worker['Image']},
 'resource_scope':'Job containers only; the shared isolated Docker parent remains memory bounded. Browser subprocess containers keep original Jenkinsfile limits.'}
(output/'identity.json').write_text(json.dumps(identity))
print('Jenkins candidate '+COMMIT+' build '+str(number),flush=True)
started=time.time();deadline=time.monotonic()+2100;previous=None
while time.monotonic()<deadline:
 try:build=jenkins("print(request('/job/antares-ci/"+str(number)+"/api/json?tree=number,result,building,duration,timestamp').decode())")
 except subprocess.CalledProcessError:
  time.sleep(10);continue
 if build!=previous:
  print(json.dumps(build),flush=True);previous=build
 try:
  stats=[json.loads(line) for line in docker('stats','--no-stream','--format','{{json .}}',timeout=15).splitlines() if line]
  sample={'at':time.time(),'containers':[{key:row[key] for key in ('ID','Name','CPUPerc','MemUsage','PIDs')} for row in stats]}
 except (subprocess.SubprocessError,ValueError,KeyError) as error:sample={'at':time.time(),'sampling_error':type(error).__name__}
 with (output/'resource-samples.jsonl').open('a') as stream:stream.write(json.dumps(sample)+'\n')
 if not build['building']:break
 time.sleep(30)
else:raise TimeoutError('Original Jenkins run did not finish; no forced cancellation or retry')
"""

COLLECT_AND_RESTORE = r"""
evidence=jenkins('JOB="antares-ci"\nNUMBER='+str(number)+'\n'+COLLECT)
assert not evidence['build']['building'] and COMMIT in evidence['build']['checkout_revisions']
(output/'jenkins-evidence.json').write_text(json.dumps(evidence))
events=docker('events','--since',str(int(started)),'--until',str(int(time.time())+1),'--filter','event=oom','--format','{{json .}}',timeout=30)
(output/'oom-events.json').write_text(json.dumps([json.loads(line) for line in events.splitlines() if line]))
groovy='''import jenkins.model.Jenkins
import hudson.slaves.EnvironmentVariablesNodeProperty
def instance=Jenkins.get()
assert !instance.items.any { it.lastBuild?.building }
def property=instance.globalNodeProperties.get(EnvironmentVariablesNodeProperty)
assert property!=null && property.envVars.get('NODE_OPTIONS')=='--max-old-space-size=2048'
property.envVars.remove('NODE_OPTIONS')
instance.save()
println('Antares test budget restored')
'''
message=jenkins('print(json.dumps(request("/scriptText",urllib.parse.urlencode({"script":'+repr(groovy)+'}).encode()).decode()))')
assert message.strip()=='Antares test budget restored'
docker('stop','--time','120','jenkins-parity',timeout=150)
docker('update','--memory','2g','--memory-swap','4g','--cpus','2','jenkins-parity')
assert not json.loads(docker('inspect','jenkins-parity'))[0]['State']['Running']
(output/'jenkins-restored.json').write_text(json.dumps({'stopped':True,'memory':'2g','cpus':2,'node_options_removed':True}))
print('Actual Jenkins outcome: '+evidence['build']['result']+'; owned Jenkins stopped and temporary budget restored.',flush=True)
"""

RECOVERY = r"""
import json,pathlib,subprocess,time
output=pathlib.Path('evidence');output.mkdir()
def docker(*args,timeout=60):return subprocess.check_output(['docker',*args],text=True,timeout=timeout)
info=json.loads(docker('inspect','jenkins-parity'))[0]
assert info['Id']==EXPECTED_ID and info['State']['Running']
assert info['HostConfig']['Memory']==IDENTITY['jenkins_memory']
assert info['HostConfig']['NanoCpus']==int(IDENTITY['jenkins_cpus']*1e9)
def jenkins(script):
 return json.loads(subprocess.check_output(['docker','exec','-i','jenkins-parity','python3','-'],input=AUTH+'\n'+script,text=True,timeout=90))
state=jenkins("print(request('/api/json?tree=jobs[name,lastBuild[building]]').decode())")
assert not any((job.get('lastBuild') or {}).get('building') for job in state['jobs'])
assert not jenkins("print(request('/queue/api/json?tree=items[id]').decode())")['items']
number=IDENTITY['number']
build=jenkins("print(request('/job/antares-ci/"+str(number)+"/api/json?tree=number,result,building,duration,timestamp').decode())")
assert not build['building'] and build['result']
started=build['timestamp']/1000
(output/'identity.json').write_text(json.dumps(IDENTITY))
print('Collecting completed build '+str(number)+' after observer interruption; no build started.',flush=True)
"""

AUTH = r"""
import base64,http.cookiejar,json,os,urllib.request,urllib.parse
opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
headers={'Authorization':'Basic '+base64.b64encode(('admin:'+os.environ['PARITY_PASSWORD']).encode()).decode()}
def request(path,data=None):
 with opener.open(urllib.request.Request('http://127.0.0.1:8080'+path,headers=headers,data=data),timeout=30) as response:return response.read()
crumb=json.loads(request('/crumbIssuer/api/json'));headers[crumb['crumbRequestField']]=crumb['crumb']
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--recover-observer", action="store_true", help="Collect an already completed build after its observer lost its lease")
    parser.add_argument("--cpus", type=int, choices=[2, 6], default=6)
    parser.add_argument("--memory", choices=["3g", "4g"], default="3g")
    parser.add_argument("--attempt", default="", help="Distinct, explicitly prepared comparison attempt")
    parser.add_argument("--previous-attempt", help="Explicit retained comparison directory for a setup correction")
    parser.add_argument("--checkout", default=str(ROOT / ".sources/antares-nas-validation"))
    parser.add_argument("--temporary-storage", action="store_true", help="Require the recorded equivalent disposable helper storage policy")
    parser.add_argument("--execution-pool", help="Recorded dedicated Linux pool; controller stays on NAS")
    parser.add_argument("--setup-retry", help="Distinct observer suffix after a retained failure before any Jenkins build")
    args = parser.parse_args()
    assert not args.attempt or re.fullmatch(r"[a-z][a-z0-9-]{0,23}", args.attempt)
    checkout = (ROOT / args.checkout).resolve()
    assert checkout.is_relative_to((ROOT / ".sources").resolve())
    assert not args.previous_attempt or (args.attempt and re.fullmatch(r"[a-z][a-z0-9-]{0,40}", args.previous_attempt))
    commit = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"],text=True).strip()
    assert re.fullmatch("[a-f0-9]{40}", commit)
    assert not subprocess.check_output(["git", "-C", str(checkout), "status", "--porcelain"]).strip()
    folder = ROOT / "test-results/nas-parity/followup/candidates/antares" / commit
    if args.attempt:
        previous_attempt = args.previous_attempt or ('without-tmpfs' if args.temporary_storage else 'production-contention')
        assert (folder/'attempts'/previous_attempt/'comparison.json').is_file(), (
            'An explicit retry must retain its preceding comparison'
        )
    source = "http://gitea:3000/gitea-admin/antares-candidate-" + commit[:12] + ".git"
    pool = None
    expected_id = JENKINS_ID
    profile = "antares"
    if args.execution_pool:
        pool_path = (ROOT / args.execution_pool).resolve()
        assert pool_path.is_relative_to((ROOT / "test-results/nas-parity/followup/linux-pool").resolve())
        pool = json.loads(pool_path.read_text())
        preflight = json.loads(pool_path.with_name("preflight.json").read_text())
        assert preflight["passed"] and preflight["candidate"] == commit and preflight["parent_id"] == pool["parent_id"]
        assert pool["candidate"] == commit and pool["source"] == source
        assert pool["controller"] == "http://192.168.178.97:8088" and not pool["production_modified"]
        expected_id, profile = pool["jenkins_id"], pool["profile"]
        assert profile == "antares-linux" and re.fullmatch(r"[a-f0-9]{64}", expected_id)
        assert args.memory == "4g" and args.cpus == 6 and not args.recover_observer
    if args.memory == "4g":
        proof = json.loads((folder / "local-linux-unit-six-cpu-four-gib.json").read_text())
        assert args.cpus == 6 and proof["passed"] and not proof["oom_events"] and proof["candidate"] == commit
    values = {"COMMIT":commit,"SOURCE":source,"EXPECTED_ID":expected_id,"AUTH":AUTH,"COLLECT":in_container(COLLECT),"JOB_CPUS":args.cpus,"JOB_MEMORY":int(args.memory[0])*1024**3}
    temporary = None
    if args.temporary_storage:
        if pool:
            temporary = {"candidate": commit, "policy_sha256": pool["policy_sha256"],
                         "jenkinsfile_and_application_sources_unchanged": True,
                         "original_assertions_and_timeouts_unchanged": True,
                         "assertion_timeout_reference": "Same frozen candidate before/after storage policy; excludes original application baseline",
                         "execution_host": pool["execution_host"], "browser_tmpfs": "1g", "database_storage": "disk"}
        else:
            temporary = json.loads((folder/'tmpfs-policy-applied.json').read_text())
        assert temporary['candidate']==commit and temporary['jenkinsfile_and_application_sources_unchanged']
        assert temporary['original_assertions_and_timeouts_unchanged']
        import hashlib
        policy_path = ROOT / (".local/nas-linux-pool/fixtures/antares-docker.py" if pool else "infra/nas/antares-docker.py")
        assert temporary['policy_sha256']==hashlib.sha256(policy_path.read_bytes()).hexdigest()
        values['TEMPORARY_STORAGE_POLICY']=temporary['policy_sha256']
    observer_name = 'antares-jenkins-'+commit[:12]
    if pool:
        observer_name += '-linux-pool'
    if args.setup_retry:
        assert pool and re.fullmatch(r"[a-z][a-z0-9-]{0,23}", args.setup_retry)
        previous_observer = ROOT / 'test-results/nas-parity/followup' / observer_name
        previous_run = json.loads((previous_observer / 'run.json').read_text())
        assert previous_run['status'] == 'failed'
        assert not (previous_observer / 'leroy-artifacts/probe/evidence/identity.json').exists()
        observer_name += '-' + args.setup_retry
    if args.cpus == 2:
        observer_name += '-cpu2'
    if args.attempt:
        observer_name += '-' + args.attempt
    original_archive = None
    if args.recover_observer:
        previous = ROOT / 'test-results/nas-parity/followup' / observer_name
        failed = json.loads((previous/'run.json').read_text())
        assert failed['status']=='cancelled' and failed['reason']=='Controller lease could not be renewed'
        original_archive = previous/'leroy-artifacts/probe/evidence'
        values['IDENTITY'] = json.loads((original_archive/'identity.json').read_text())
        assert values['IDENTITY']['candidate']==commit and values['IDENTITY']['jenkins_container_id']==JENKINS_ID
        observer_name += '-recover'
    policy_preflight = ''
    if temporary:
        policy_preflight = r'''
import hashlib,os,pathlib,subprocess
assert os.environ['LEROY_NAS_ANTARES_TMPFS']=='1'
assert hashlib.sha256(pathlib.Path('/usr/local/bin/docker').read_bytes()).hexdigest()==TEMPORARY_STORAGE_POLICY
assert subprocess.check_output(['docker','exec','jenkins-parity','python3','-c',"import hashlib,pathlib;print(hashlib.sha256(pathlib.Path('/usr/local/bin/docker').read_bytes()).hexdigest())"],text=True).strip()==TEMPORARY_STORAGE_POLICY
'''
    # The Jenkins process must be started by PROGRAM before its policy can be read.
    body = RECOVERY if args.recover_observer else PROGRAM
    if temporary:
        assert not args.recover_observer, 'Inspect a failed observer explicitly before resuming'
        anchor="def jenkins(script):\n"
        assert body.count(anchor)==1
        body=body.replace(anchor,policy_preflight+'\n'+anchor,1)
    program = "\n".join(key+"="+repr(value) for key,value in values.items()) + "\n" + body + COLLECT_AND_RESTORE
    for label, text in (("antares-comparison",program),("jenkins-auth",AUTH),("collector",values["COLLECT"])):
        compile(text,label,"exec")
    if args.prepare_only:
        print(json.dumps({"candidate":commit,"remote_actions":False,"profile":profile}))
        return
    staged=json.loads((folder/'staged.json').read_text())
    assert staged['source']==source and staged['jenkinsfiles_unchanged']
    assert subprocess.check_output(["git", "-C", str(checkout), "show", staged['original_commit'] + ":Jenkinsfile"]) == subprocess.check_output(["git", "-C", str(checkout), "show", commit + ":Jenkinsfile"])
    assert not (folder/'comparison.json').exists(), "No implicit comparison rerun"
    if not args.recover_observer:
        production_before = wait_production_jobs()
        wait_production_build()
    diagnostic,run=execute(observer_name,program,timeout=300 if args.recover_observer else 2700,artifacts=['evidence/**'],poll_seconds=15,profile=profile)
    archive=diagnostic/'leroy-artifacts/probe/evidence'
    evidence=json.loads((archive/'jenkins-evidence.json').read_text())
    identity=json.loads((archive/'identity.json').read_text())
    state={'commit':commit,'original_commit':staged['original_commit'],'application_patches_applied':True,
           'jenkins_number':identity['number'],'jenkins':evidence['build'],'jenkins_transport_run':run['id'],
           'resource_comparison':identity,'jenkins_restored':json.loads((archive/'jenkins-restored.json').read_text())}
    if temporary:
        state['temporary_storage_policy']=temporary
    if pool:
        state['execution_pool'] = pool
        state['distributed_worker_preflight'] = preflight
    if args.setup_retry:
        state['pre_build_setup_failure'] = {'observer_run': previous_run['id'], 'correction': args.setup_retry,
                                           'previous_build_started': False}
    if not args.recover_observer:
        state['production_jobs_before']=production_before
        state['production_jobs_after']=production_jobs()
        state['production_jobs_unchanged']=state['production_jobs_before']['jobs']==state['production_jobs_after']['jobs']
    history = folder/'attempts/six-cpu/comparison.json'
    if history.exists():
        state['previous_comparison'] = history.relative_to(ROOT).as_posix()
    if args.attempt:
        state['comparison_attempt'] = args.attempt
        history = folder/'attempts'/previous_attempt/'comparison.json'
        assert history.is_file(), 'An explicit retry must retain its preceding comparison'
        state['previous_comparison'] = history.relative_to(ROOT).as_posix()
    for name in ('jenkins-console.log','jenkins-'+str(identity['number'])+'-console.log'):
        (folder/name).write_text(evidence['console'],encoding='utf-8')
    for name in ('jenkins-before.xml','jenkins-candidate.xml'):
        (folder/name).write_bytes(((original_archive or archive)/name).read_bytes())
    if args.recover_observer:
        state['observer_interruption']={'run':failed['id'],'reason':failed['reason'],'build_restarted':False}
    (folder/'comparison.json').write_text(json.dumps(state,indent=2)+'\n')
    print(json.dumps(state),flush=True)
    assert evidence['build']['result']=='SUCCESS', 'Actual failed gates retained; no false acceptance'


if __name__ == '__main__':
    main()

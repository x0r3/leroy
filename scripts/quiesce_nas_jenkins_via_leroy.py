"""Stop only the completed, owned comparison Jenkins and its isolated builders."""

import json
import time

from nas_candidate_paths import comparison_source
from nas_diagnostic import execute
from watch_nas_graphato_via_leroy import JENKINS_ID

PROGRAM = r"""
import json,pathlib,subprocess
info=json.loads(subprocess.check_output(['docker','inspect','jenkins-parity'],text=True))[0]
assert info['Id']==EXPECTED_ID
state={'jenkins_container_id':info['Id'],'builders':[]}
if info['State']['Running']:
 script='''import base64,json,os,urllib.request
headers={'Authorization':'Basic '+base64.b64encode(('admin:'+os.environ['PARITY_PASSWORD']).encode()).decode()}
def get(path):
 with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8080'+path,headers=headers),timeout=30) as response:return json.load(response)
jobs=get('/api/json?tree=jobs[name,lastBuild[building]]')['jobs']
queue=get('/queue/api/json?tree=items[id]')['items']
assert not any((job.get('lastBuild') or {}).get('building') for job in jobs) and not queue
print(json.dumps({'jobs':jobs,'queue':queue}))
'''
 state['idle']=json.loads(subprocess.check_output(['docker','exec','jenkins-parity','python3','-c',script],text=True,timeout=60))
 subprocess.run(['docker','stop','--time','120','jenkins-parity'],check=True,timeout=150)
for name in ['buildx_buildkit_graphato-registry-ci0','buildx_buildkit_leroy-graphato-nas-parity0']:
 result=subprocess.run(['docker','inspect',name],capture_output=True,text=True,timeout=30)
 if result.returncode:
  assert 'No such object' in result.stderr
  continue
 builder=json.loads(result.stdout)[0]
 assert builder['Config']['Image']=='moby/buildkit:v0.28.1'
 if builder['State']['Running']:subprocess.run(['docker','stop','--time','30',name],check=True,timeout=60)
 state['builders'].append({'name':name,'id':builder['Id'],'previously_running':builder['State']['Running']})
assert not json.loads(subprocess.check_output(['docker','inspect','jenkins-parity'],text=True))[0]['State']['Running']
state.update(candidate=CANDIDATE,stopped=True)
pathlib.Path('quiesced.json').write_text(json.dumps(state))
"""


def quiesce(candidate):
    _, folder = comparison_source("graphato-ci", candidate)
    target = json.loads((folder / "jenkins-final-state.json").read_text())
    assert target["receipt"]["commit"] == candidate and target["receipt"]["status"] == "verified"
    for job in (
        "graphato-ci",
        "graphato-release-acceptance",
        "graphato-postdeploy-web",
        "graphato-postdeploy-quality",
    ):
        pair = json.loads((folder.parent / job / "pair.json").read_text())
        assert pair["jenkins"]["result"] == "SUCCESS" and not pair["jenkins"]["building"]
    diagnostic, run = execute(
        "graphato-jenkins-stop-" + candidate[:12] + "-" + str(time.time_ns()),
        "EXPECTED_ID=" + repr(JENKINS_ID) + "\nCANDIDATE=" + repr(candidate) + "\n" + PROGRAM,
        timeout=300,
        artifacts=["quiesced.json"],
    )
    state = json.loads((diagnostic / "leroy-artifacts/probe/quiesced.json").read_text())
    assert state["candidate"] == candidate and state["stopped"]
    return {"diagnostic_run": run["id"], **state}

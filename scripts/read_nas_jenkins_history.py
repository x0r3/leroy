"""Read selected production Jenkins history without changing jobs or running builds."""

import json
from datetime import datetime, timezone

from nas_ssh import ROOT, run_script

PROGRAM = r"""
import base64,hashlib,json,os,re,urllib.request
password=os.environ['JENKINS_ADMIN_PASSWORD']
headers={'Authorization':'Basic '+base64.b64encode((os.environ['JENKINS_ADMIN_ID']+':'+password).encode()).decode()}
def get(path):
 with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8080'+path,headers=headers),timeout=30) as response:return response.read()
result={}
for name in ['antares-ci','graphato-ci','graphato-postdeploy-web','graphato-postdeploy-quality','graphato-release-acceptance']:
 job=json.loads(get('/job/'+name+'/api/json?tree=lastBuild[number],lastSuccessfulBuild[number]'))
 builds={}
 for number in sorted({v['number'] for k,v in job.items() if isinstance(v,dict) and 'number' in v}):
  path='/job/'+name+'/'+str(number)
  meta=json.loads(get(path+'/api/json?tree=number,result,building,timestamp,duration,actions[lastBuiltRevision[SHA1]]'))
  log=get(path+'/consoleText').decode(errors='replace').replace(password,'[REDACTED]')
  meta['console_sha256']=hashlib.sha256(log.encode()).hexdigest()
  meta['evidence_lines']=[line for line in log.splitlines() if re.search(r'Checking out Revision|Finished:|npm audit|vulnerabilit|Error:|ValueError|permission|Permission|Run markers|Tests:|Test Suites:|passed|failed|Failure|FAIL|postdeploy|release-status|Build number|commit=',line)][-160:]
  builds[str(number)]=meta
 result[name]={'job':job,'builds':builds}
print(json.dumps(result))
"""


def main():
    bridge = (
        "import subprocess\np=subprocess.run(['docker','exec','-i','jenkins','python3','-'],input="
        + repr(PROGRAM)
        + ",text=True,capture_output=True,timeout=150)\nprint(p.stdout)\nraise SystemExit(p.returncode)\n"
    )
    result = run_script("python3 - <<'PY'\n" + bridge + "PY\n", ROOT / ".local/nas-ssh.json", timeout=180)
    if result.returncode:
        raise RuntimeError("Read-only production history query failed")
    history = json.loads(result.stdout)
    folder = ROOT / "test-results/nas-parity/followup"
    folder.mkdir(exist_ok=True)
    path = folder / "production-jenkins-history.json"
    assert not path.exists(), "Preserve previous production observations"
    path.write_text(
        json.dumps({"at": datetime.now(timezone.utc).isoformat(), "jobs": history}, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                name: {
                    "last": value["job"].get("lastBuild"),
                    "last_success": value["job"].get("lastSuccessfulBuild"),
                    "results": {n: b["result"] for n, b in value["builds"].items()},
                }
                for name, value in history.items()
            }
        )
    )


if __name__ == "__main__":
    main()

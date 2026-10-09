"""Connect original-source Graphato jobs exclusively to owned NAS test services."""

import json
import re

from compare_nas_antares import jenkins_python
from deploy_nas_parity import CREDENTIALS, remote
from nas_gitea_target import idle
from nas_ssh import ROOT, run_script
from prepare_nas_gitea import AUTH

RESULTS = ROOT / "test-results/nas-parity"


def main():
    idle()
    marker = RESULTS / "graphato-services-ready.json"
    if marker.exists():
        raise RuntimeError("Graphato service setup already recorded")
    assert (RESULTS / "aligned/gitea-bootstrap-repo/leroy-target-state.json").exists()
    baseline = json.loads((RESULTS / "baseline.json").read_text())
    commits = {
        name: baseline["sources"][name]["commit"] for name in ("graphato", "home-lab-service-collection")
    }
    remote(
        'test "$(docker exec leroy-nas-parity-docker-1 docker inspect --format \'{{index .Config.Labels "io.leroy.nas-parity"}}\' gitea)" = true\n'
    )
    program = """import base64,json,os,pathlib,subprocess,time,urllib.request,urllib.error
credentials=json.load(open('/fixtures/gitea-test-credential.json'))
headers={'Authorization':'Basic '+base64.b64encode((credentials['user']+':'+credentials['password']).encode()).decode(),'Content-Type':'application/json'}
base='http://gitea:3000'
def request(path,data=None):
 with urllib.request.urlopen(urllib.request.Request(base+'/api/v1'+path,headers=headers,data=json.dumps(data).encode() if data is not None else None),timeout=20) as response:return json.load(response)
askpass=pathlib.Path('/tmp/leroy-parity-gitea-askpass.py')
askpass.write_text(ASKPASS)
askpass.chmod(0o700)
env={**os.environ,'GIT_ASKPASS':str(askpass),'GIT_TERMINAL_PROMPT':'0'}
observed={}
for name,commit in COMMITS.items():
 try:request('/repos/gitea-admin/'+name)
 except urllib.error.HTTPError as error:
  if error.code != 404:raise
  request('/user/repos',{'name':name,'private':True,'default_branch':'master','auto_init':False})
 source='/sources/'+name
 assert subprocess.check_output(['git','--git-dir',source,'rev-parse','master'],text=True).strip()==commit
 subprocess.run(['git','-c','safe.directory='+source,'--git-dir',source,'push',base+'/gitea-admin/'+name+'.git',commit+':refs/heads/master'],env=env,check=True,capture_output=True)
 deadline=time.monotonic()+30
 while True:
  try:
   observed[name]=request('/repos/gitea-admin/'+name+'/branches/master')['commit']['id']
   break
  except urllib.error.HTTPError as error:
   if error.code != 404 or time.monotonic()>=deadline:raise
   time.sleep(1)
assert observed==COMMITS
print(json.dumps(observed))
"""
    askpass = "#!/usr/bin/python3\nimport json,sys\nc=json.load(open('/fixtures/gitea-test-credential.json'))\nprint(c['user'] if 'username' in sys.argv[1].lower() else c['password'])\n"
    seeded = json.loads(
        jenkins_python("COMMITS=" + repr(commits) + "\nASKPASS=" + repr(askpass) + "\n" + program)
    )
    info = run_script("docker exec leroy-nas-parity-docker-1 docker inspect registry\n", CREDENTIALS)
    assert info.returncode == 0
    registry = json.loads(info.stdout)[0]
    assert registry["Config"]["Labels"]["io.leroy.nas-parity"] == "true"
    volume = next(m["Name"] for m in registry["Mounts"] if m["Destination"] == "/var/lib/registry")
    assert re.fullmatch(r"[0-9a-f]{64}", volume)
    ip = "10.234.98.2"
    image = registry["Image"]
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", image)
    remote(f"""docker exec leroy-nas-parity-docker-1 docker stop registry
docker exec leroy-nas-parity-docker-1 docker network disconnect leroy-jobs registry
docker exec leroy-nas-parity-docker-1 docker rename registry registry-before-loopback
docker exec leroy-nas-parity-docker-1 docker run -d --name registry --network leroy-jobs --ip {ip} --label io.leroy.nas-parity=true -p 127.0.0.1:5005:5000 -v {volume}:/var/lib/registry {image}
""")
    groovy = """import jenkins.model.Jenkins
import hudson.slaves.EnvironmentVariablesNodeProperty
def instance=Jenkins.get()
def property=instance.globalNodeProperties.get(EnvironmentVariablesNodeProperty)
if (property==null) { property=new EnvironmentVariablesNodeProperty();instance.globalNodeProperties.add(property) }
property.envVars.put('GRAPHATO_CI_HOST_HOME','/var/lib/docker/volumes/jenkins-parity-aligned-home/_data')
instance.save()
println('Owned Jenkins workspace mapping saved')
"""
    result = jenkins_python(
        AUTH
        + "print(request('/scriptText',urllib.parse.urlencode({'script':"
        + repr(groovy)
        + "}).encode()).decode())\n"
    )
    assert result.strip() == "Owned Jenkins workspace mapping saved"
    for name, parameters in {
        "graphato-bootstrap-host": {
            "TARGET_HOST": "graphato-vm",
            "DOMAIN": "graphato.test",
            "GRAPHATO_REF": commits["graphato"],
            "APPLY_CHANGES": True,
        },
        "graphato-ci": {},
        "graphato-release-acceptance": {"RELEASE_COMMIT": commits["graphato"]},
        "graphato-postdeploy-web": {"RELEASE_COMMIT": commits["graphato"], "CHECK_GROUP": "all"},
        "graphato-postdeploy-quality": {"RELEASE_COMMIT": commits["graphato"], "CHECK_GROUP": "all"},
    }.items():
        folder = RESULTS / "aligned" / name
        folder.mkdir(exist_ok=True)
        path = folder / "prepared.json"
        assert not path.exists()
        path.write_text(json.dumps({"parameters": parameters, "automatic_triggers": False}, indent=2) + "\n")
    marker.write_text(
        json.dumps(
            {
                "seeded_commits": seeded,
                "registry": {
                    "address": "127.0.0.1:5005",
                    "scope": "nested Docker loopback only",
                    "preserved_volume": volume,
                },
                "jenkins_home_mapping": "/var/lib/docker/volumes/jenkins-parity-aligned-home/_data",
                "application_sources_modified": False,
            },
            indent=2,
        )
        + "\n"
    )
    print("Original repositories, nested registry and Jenkins workspace mapping prepared")


if __name__ == "__main__":
    main()

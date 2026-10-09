"""Create equivalent fresh Gitea targets only inside the owned nested daemon."""

import argparse
import json
from contextlib import closing

from compare_nas_antares import client, jenkins_python
from deploy_nas_parity import remote
from nas_followup_support import inner
from nas_ssh import ROOT
from nas_target_images import import_production_image
from prepare_nas_gitea import AUTH

OUTPUT = ROOT / "test-results/nas-parity/aligned/gitea-bootstrap-repo"


def idle():
    running = json.loads(inner("inspect", "jenkins-parity", "--format", "{{json .State.Running}}"))
    if running:
        result = json.loads(
            jenkins_python(AUTH + "print(request('/api/json?tree=jobs[lastBuild[building]]').decode())\n")
        )
        assert not any(j.get("lastBuild") and j["lastBuild"]["building"] for j in result["jobs"])
    with closing(client()) as api:
        for status in ("running", "queued", "waiting"):
            response = api.get("/api/runs", params={"status": status, "limit": 100})
            response.raise_for_status()
            assert not response.json(), "Complete the current Leroy comparison first"


def create(engine):
    idle()
    path = OUTPUT / (engine + "-target.json")
    if path.exists():
        raise RuntimeError("Target already recorded; no implicit replacement")
    if engine == "jenkins":
        identity = import_production_image("gitea")["nested_id"]
    else:
        previous = json.loads((OUTPUT / "jenkins-target.json").read_text())
        identity = previous["image"]
        pair = json.loads((OUTPUT / "pair.json").read_text())
        assert pair["jenkins"]["result"] and not pair["jenkins"]["building"]
        assert (OUTPUT / "jenkins-target-state.json").exists()
        remote("""test "$(docker exec leroy-nas-parity-docker-1 docker inspect --format '{{index .Config.Labels "io.leroy.nas-parity"}}' gitea)" = true
docker exec leroy-nas-parity-docker-1 docker stop gitea
docker exec leroy-nas-parity-docker-1 docker network disconnect leroy-jobs gitea
docker exec leroy-nas-parity-docker-1 docker rename gitea gitea-parity-jenkins
""")
    remote(f"""docker exec leroy-nas-parity-docker-1 docker run -d --name gitea \
 --label io.leroy.nas-parity=true --network leroy-jobs --memory 384m --cpus 0.5 \
 -v gitea-parity-{engine}-data:/data \
 -e GITEA__security__INSTALL_LOCK=true -e GITEA__database__DB_TYPE=sqlite3 \
 -e GITEA__server__ROOT_URL=http://gitea:3000 -e GITEA__service__DISABLE_REGISTRATION=true {identity}
""")
    path.write_text(
        json.dumps({"image": identity, "volume": f"gitea-parity-{engine}-data", "fresh": True}, indent=2)
        + "\n"
    )
    print("Fresh Gitea target created for", engine)


def capture(engine):
    result = jenkins_python("""import base64,json,urllib.request
credentials=json.load(open('/fixtures/gitea-test-credential.json'))
headers={'Authorization':'Basic '+base64.b64encode((credentials['user']+':'+credentials['password']).encode()).decode()}
def get(path):
 with urllib.request.urlopen(urllib.request.Request('http://gitea:3000/api/v1'+path,headers=headers),timeout=20) as r:return json.load(r)
repo=get('/repos/gitea-admin/home-lab-service-collection'); user=get('/user')
print(json.dumps({'version':get('/version')['version'], 'user':{k:user[k] for k in ('login','email','is_admin','active')},'repository':{k:repo[k] for k in ('name','full_name','private','empty','default_branch')}}))
""")
    value = json.loads(result)
    (OUTPUT / (engine + "-target-state.json")).write_text(json.dumps(value, indent=2) + "\n")
    print(json.dumps(value, indent=2))
    if engine == "leroy":
        previous = json.loads((OUTPUT / "jenkins-target-state.json").read_text())
        assert previous == value, "Observed Gitea target states differ"


def ready(engine):
    version = json.loads(
        jenkins_python(
            "import json,urllib.request\nwith urllib.request.urlopen('http://gitea:3000/api/v1/version',timeout=10) as response: print(response.read().decode())\n"
        )
    )
    path = OUTPUT / (engine + "-target.json")
    state = json.loads(path.read_text())
    state.update(ready=True, version=version["version"])
    path.write_text(json.dumps(state, indent=2) + "\n")
    print("Gitea target ready:", version["version"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["create", "ready", "capture"])
    parser.add_argument("engine", choices=["jenkins", "leroy"])
    args = parser.parse_args()
    {"create": create, "ready": ready, "capture": capture}[args.phase](args.engine)


if __name__ == "__main__":
    main()

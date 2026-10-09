"""Fresh Paperless API targets using the production images and private databases."""

import argparse
import json

from compare_nas_antares import jenkins_python
from deploy_nas_parity import CREDENTIALS, LOCAL, REMOTE, remote
from nas_gitea_target import idle
from nas_ssh import ROOT, run_script, upload_file
from nas_target_images import import_production_image

OUTPUT = ROOT / "test-results/nas-parity/aligned/paperless-ngx-bootstrap-rules"
NAMES = ("paperless-test", "paperless-db-test", "paperless-redis-test")


def create(engine):
    idle()
    marker = OUTPUT / (engine + "-target.json")
    if marker.exists():
        raise RuntimeError("Paperless target already recorded")
    if engine == "jenkins":
        images = {
            name: import_production_image(name)["nested_id"]
            for name in ("paperless", "paperless-db", "paperless-redis")
        }
    else:
        images = json.loads((OUTPUT / "jenkins-target.json").read_text())["images"]
        assert (OUTPUT / "jenkins-target-state.json").exists()
        for name in NAMES:
            remote(f"""test "$(docker exec leroy-nas-parity-docker-1 docker inspect --format '{{{{index .Config.Labels "io.leroy.nas-parity"}}}}' {name})" = true
docker exec leroy-nas-parity-docker-1 docker stop {name}
docker exec leroy-nas-parity-docker-1 docker network disconnect leroy-jobs {name}
docker exec leroy-nas-parity-docker-1 docker rename {name} {name}-jenkins
""")
    private = LOCAL / "config/test-secrets"
    password = (private / "paperless-db-password").read_text()
    values = {
        "PAPERLESS_REDIS": "redis://paperless-redis-test:6379",
        "PAPERLESS_DBHOST": "paperless-db-test",
        "PAPERLESS_DBNAME": "paperless",
        "PAPERLESS_DBUSER": "paperless",
        "PAPERLESS_DBPASS": password,
        "PAPERLESS_ADMIN_USER": (private / "paperless-user").read_text(),
        "PAPERLESS_ADMIN_PASSWORD": (private / "paperless-password").read_text(),
        "PAPERLESS_SECRET_KEY": (private / "app-salt").read_text(),
        "PAPERLESS_TIME_ZONE": "Europe/Berlin",
        "PAPERLESS_URL": "http://paperless-test:8000",
        "PAPERLESS_TASK_WORKERS": "1",
        "PAPERLESS_THREADS_PER_WORKER": "1",
    }
    env = LOCAL / "fixtures/paperless-test.env"
    env.write_text("".join(key + "=" + value + "\n" for key, value in values.items()))
    db = LOCAL / "fixtures/paperless-db-test.env"
    db.write_text("POSTGRES_DB=paperless\nPOSTGRES_USER=paperless\nPOSTGRES_PASSWORD=" + password + "\n")
    for path in (env, db):
        upload_file(path, REMOTE + "/fixtures/" + path.name, CREDENTIALS)
    remote(f"""docker exec leroy-nas-parity-docker-1 docker run -d --name paperless-db-test \
 --network leroy-jobs --label io.leroy.nas-parity=true --memory 256m --cpus 0.5 \
 --env-file /fixtures/paperless-db-test.env -v paperless-{engine}-database:/var/lib/postgresql/data {images["paperless-db"]}
docker exec leroy-nas-parity-docker-1 docker run -d --name paperless-redis-test \
 --network leroy-jobs --label io.leroy.nas-parity=true --memory 96m --cpus 0.25 \
 -v paperless-{engine}-redis:/data {images["paperless-redis"]}
docker exec leroy-nas-parity-docker-1 docker run -d --name paperless-test \
 --network leroy-jobs --label io.leroy.nas-parity=true --memory 1280m --cpus 1 \
 --env-file /fixtures/paperless-test.env -v paperless-{engine}-data:/usr/src/paperless/data \
 -v paperless-{engine}-media:/usr/src/paperless/media {images["paperless"]}
""")
    marker.write_text(
        json.dumps(
            {
                "images": images,
                "fresh": True,
                "engine": engine,
                "database": "isolated PostgreSQL 16",
                "ready": False,
            },
            indent=2,
        )
        + "\n"
    )
    print("Fresh Paperless target created for", engine)


def ready(engine):
    result = run_script(
        "docker exec leroy-nas-parity-docker-1 docker inspect --format '{{.State.Health.Status}}' paperless-test\n",
        CREDENTIALS,
    )
    state = result.stdout.strip()
    if result.returncode or state != "healthy":
        raise RuntimeError("Paperless is not ready: " + state)
    marker = OUTPUT / (engine + "-target.json")
    value = json.loads(marker.read_text())
    value["ready"] = True
    marker.write_text(json.dumps(value, indent=2) + "\n")
    print("Paperless target healthy")


def capture(engine):
    program = """import json,urllib.request,urllib.parse
credentials=json.load(open('/fixtures/operations-credentials.json'))
base='http://paperless-test:8000'
request=urllib.request.Request(base+'/api/token/',data=urllib.parse.urlencode({'username':credentials['paperless-user'],'password':credentials['paperless-password']}).encode())
with urllib.request.urlopen(request,timeout=30) as response:token=json.load(response)['token']
rules={}
for resource in ['tags','document_types','correspondents','storage_paths']:
 url=base+'/api/'+resource+'/?page_size=1000'; rows=[]
 while url:
  request=urllib.request.Request(url,headers={'Authorization':'Token '+token})
  with urllib.request.urlopen(request,timeout=30) as response:value=json.load(response)
  rows.extend(value['results']);url=value.get('next')
 # Exclude generated identities, counts and access-control serialization.
 keys=['name','match','matching_algorithm','is_insensitive','color','is_inbox_tag','path']
 rules[resource]=sorted([{k:row[k] for k in keys if k in row} for row in rows],key=lambda row:row['name'])
print(json.dumps(rules))
"""
    value = json.loads(jenkins_python(program))
    path = OUTPUT / (engine + "-target-state.json")
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("Observed metadata counts:", {key: len(rows) for key, rows in value.items()})
    assert {key: len(rows) for key, rows in value.items()} == {
        "tags": 64,
        "document_types": 15,
        "correspondents": 31,
        "storage_paths": 0,
    }
    if engine == "leroy":
        assert value == json.loads((OUTPUT / "jenkins-target-state.json").read_text(encoding="utf-8"))
        print("Both engines produced identical Paperless metadata.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["create", "ready", "capture"])
    parser.add_argument("engine", choices=["jenkins", "leroy"])
    args = parser.parse_args()
    {"create": create, "ready": ready, "capture": capture}[args.phase](args.engine)


if __name__ == "__main__":
    main()

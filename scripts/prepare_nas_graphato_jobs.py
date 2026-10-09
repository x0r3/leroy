"""Prepare original Graphato jobs; application execution stays explicit."""

import json
import xml.etree.ElementTree as ET
from contextlib import closing

from compare_nas_antares import client, jenkins, jenkins_python
from deploy_nas_parity import CREDENTIALS, LOCAL, REMOTE, remote
from nas_ssh import ROOT, upload_file
from prepare_nas_gitea import AUTH

JOBS = [
    "graphato-bootstrap-host",
    "graphato-ci",
    "graphato-postdeploy-web",
    "graphato-postdeploy-quality",
    "graphato-release-acceptance",
]


def main():
    output = ROOT / "test-results/nas-parity"
    marker = output / "graphato-jobs-prepared.json"
    if marker.exists():
        raise RuntimeError("Graphato comparison jobs already prepared")
    host = (ROOT / ".local/vm/ssh_host_ed25519_key.pub").read_text().strip()
    known = LOCAL / "config/test-secrets/graphato-known-hosts"
    known.write_text("[graphato-vm]:12225 " + host + "\n")
    upload_file(known, REMOTE + "/config/test-secrets/" + known.name, CREDENTIALS)
    for name in JOBS:
        xml = ET.fromstring((output / "jenkins-configs" / (name + ".xml")).read_text())
        properties = xml.find("properties")
        for node in list(properties):
            if node.tag.endswith("PipelineTriggersJobProperty"):
                properties.remove(node)
        for triggers in xml.findall("triggers"):
            triggers.clear()
        scm = xml.find(".//scm")
        repo = "home-lab-service-collection" if name == "graphato-bootstrap-host" else "graphato"
        scm.find(".//hudson.plugins.git.UserRemoteConfig/url").text = (
            "http://gitea:3000/gitea-admin/" + repo + ".git"
        )
        scm.find(".//hudson.plugins.git.BranchSpec/name").text = "*/master"
        fixture = LOCAL / "fixtures" / (name + ".xml")
        fixture.write_text(ET.tostring(xml, encoding="unicode"), encoding="utf-8")
        upload_file(fixture, REMOTE + "/fixtures/" + fixture.name, CREDENTIALS)
    remote(f"""cd {REMOTE}
chmod 644 config/test-secrets/graphato-known-hosts fixtures/graphato-*.xml
docker exec leroy-nas-parity-docker-1 docker cp /test-secrets/deploy jenkins-parity:/root/.ssh/parity-deploy
docker exec leroy-nas-parity-docker-1 docker exec --privileged jenkins-parity chown 0:0 /root/.ssh/parity-deploy
docker exec leroy-nas-parity-docker-1 docker exec jenkins-parity chmod 600 /root/.ssh/parity-deploy
""")
    groovy = """import com.cloudbees.plugins.credentials.*
import com.cloudbees.plugins.credentials.domains.Domain
import com.cloudbees.jenkins.plugins.sshcredentials.impl.BasicSSHUserPrivateKey
def provider=SystemCredentialsProvider.getInstance()
for (name in ['bootstrap','deploy']) {
 def id='graphato-'+name+'-ssh'
 assert !provider.credentials.any { it.id == id }
 def key=new File('/root/.ssh/parity-'+name).text
 provider.getStore().addCredentials(Domain.global(),new BasicSSHUserPrivateKey(CredentialsScope.GLOBAL,id,'root',new BasicSSHUserPrivateKey.DirectEntryPrivateKeySource(key),'','Isolated VM only'))
}
provider.save()
println('Graphato test credentials installed')
"""
    response = jenkins_python(
        AUTH
        + "print(request('/scriptText',urllib.parse.urlencode({'script':"
        + repr(groovy)
        + "}).encode()).decode())\n"
    )
    if response.strip() != "Graphato test credentials installed":
        raise RuntimeError("Graphato test credential installation was not confirmed")
    config = LOCAL / "config/runner.toml"
    text = config.read_text()
    if "[profiles.graphato]" in text:
        raise RuntimeError("Graphato profile already configured")
    text += """
[profiles.graphato]
image = "leroy-job:nas-parity"
network = "leroy-jobs"
memory = "2g"
cpus = 2
docker = true
host_mappings = {controller = "10.232.98.10", graphato-vm = "10.232.98.11"}
mounts = ["type=bind,source=/fixtures/graphato-tools/bin/docker,target=/usr/local/bin/docker,readonly", "type=bind,source=/fixtures/graphato-tools/docker-config/cli-plugins,target=/usr/local/lib/docker/cli-plugins,readonly"]
[profiles.graphato.environment]
DOCKER_BUILDKIT = "1"
DOCKER_CONFIG = "/work/docker-config"
GRAPHATO_REGISTRY_PUSH = "registry:5000"
GRAPHATO_REGISTRY_API = "http://registry:5000"
[profiles.graphato.graphato]
builder_name = "leroy-graphato-nas-parity"
repository = "http://gitea:3000/gitea-admin/graphato.git"
host = "graphato-vm"
port = 12225
desktop_releases = "/leroy-graphato-releases"
[profiles.graphato.secrets.git]
GIT_USER = "/test-secrets/gitea-user"
GIT_PASSWORD = "/test-secrets/gitea-password"
[profiles.graphato.secrets."graphato-bootstrap"]
BOOTSTRAP_KEY = "/test-secrets/bootstrap"
KNOWN_HOSTS = "/test-secrets/graphato-known-hosts"
[profiles.graphato.secrets."graphato-deploy"]
DEPLOY_KEY = "/test-secrets/deploy"
KNOWN_HOSTS = "/test-secrets/graphato-known-hosts"
"""
    config.write_text(text)
    upload_file(config, REMOTE + "/config/runner.toml", CREDENTIALS)
    remote(f"""cd {REMOTE}
chmod 644 config/runner.toml
docker compose up -d --no-deps --force-recreate runner
docker exec leroy-nas-parity-docker-1 mkdir -p /leroy-graphato-releases /volume1/Releases/graphato-desktop
docker exec leroy-nas-parity-docker-1 chown 1000:10 /leroy-graphato-releases /volume1/Releases/graphato-desktop
""")
    with closing(client()) as api:
        installed = {p["id"]: p for p in api.get("/api/pipelines").json()}
        for name in JOBS:
            jenkins("configure", name)
            spec = installed[name]["spec"]
            spec.update(
                profile="graphato",
                enabled=False,
                repository="http://gitea:3000/gitea-admin/"
                + ("home-lab-service-collection" if name == "graphato-bootstrap-host" else "graphato")
                + ".git",
            )
            api.put("/api/pipelines/" + name, json=spec).raise_for_status()
    marker.write_text(
        json.dumps(
            {
                "jobs": JOBS,
                "started": False,
                "still_required": [
                    "seed original repositories",
                    "map Jenkins volume for nested bind mounts",
                    "publish isolated registry on nested loopback 5005",
                ],
            },
            indent=2,
        )
        + "\n"
    )
    print("Graphato comparison jobs prepared; no job started.")


if __name__ == "__main__":
    main()

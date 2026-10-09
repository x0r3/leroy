"""Prepare remaining operations jobs with generated credentials and owned targets."""

import argparse
import json
import secrets
import tarfile
import wave
import xml.etree.ElementTree as ET
from contextlib import closing

from compare_nas_antares import client, jenkins, jenkins_python
from deploy_nas_parity import CREDENTIALS, LOCAL, REMOTE, remote
from nas_ssh import ROOT, upload_file
from prepare_nas_gitea import AUTH

JOBS = [
    "paperless-ngx-bootstrap-rules",
    "music-library-sync-smartphone",
    "nikicas-hub-bootstrap-host",
    "nikicas-hub-deploy",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["prepare", "activate"])
    args = parser.parse_args()
    if args.phase == "activate":
        from nas_gitea_target import idle

        idle()
        remote(f"cd {REMOTE}\ndocker compose up -d --no-deps --force-recreate runner\n")
        print("Operations profiles activated while both comparison engines were idle.")
        return
    marker = ROOT / "test-results/nas-parity/operations-prepared.json"
    if marker.exists():
        raise RuntimeError("Operations jobs already prepared")
    private = LOCAL / "config/test-secrets"
    values = {
        "paperless-user": "test-admin",
        "paperless-password": secrets.token_urlsafe(32),
        "paperless-db-password": secrets.token_urlsafe(32),
        "root-user": "root",
        "hub-user": "nikicas-hub-deploy",
        "app-admin-secret": secrets.token_urlsafe(32),
        "app-salt": secrets.token_urlsafe(32),
        "event-salt": secrets.token_urlsafe(32),
    }
    for name, value in values.items():
        path = private / name
        if not path.exists():
            path.write_text(value)
        upload_file(path, REMOTE + "/config/test-secrets/" + name, CREDENTIALS)
    host_key = (ROOT / ".local/vm/ssh_host_ed25519_key.pub").read_text().strip()
    known = private / "operations-known-hosts"
    known.write_text("[parity-vm]:12225 " + host_key + "\n")
    upload_file(known, REMOTE + "/config/test-secrets/" + known.name, CREDENTIALS)
    fixture = LOCAL / "fixtures/operations-credentials.json"
    fixture.write_text(json.dumps({name: (private / name).read_text() for name in values}))
    upload_file(fixture, REMOTE + "/fixtures/" + fixture.name, CREDENTIALS)
    music = LOCAL / "fixtures/test-music"
    for name in ("library/Album/01 Test.wav", "downloads/02 Grüße.wav"):
        path = music / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as stream:
            stream.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
            stream.writeframes(b"\x00\x00\x10\x00" * 800)
    (music / "library/excluded.tmp").write_text("Must be excluded")
    (music / "downloads/.DS_Store").write_text("Must be excluded")
    archive = LOCAL / "music-fixture.tar"
    with tarfile.open(archive, "w") as bundle:
        bundle.add(music, "test-music")
    upload_file(archive, REMOTE + "/music-fixture.tar", CREDENTIALS)
    cases = json.loads((ROOT / "examples/migration-cases.json").read_text())
    parameters = {name: next(c["parameters"] for c in cases if c["pipeline"] == name) for name in JOBS}
    parameters[JOBS[0]].update(
        PAPERLESS_API_URL="http://paperless-test:8000",
        PAPERLESS_API_TOKEN_CREDENTIALS_ID="",
        PAPERLESS_API_USER_CREDENTIALS_ID="paperless-api-user",
    )
    parameters[JOBS[1]].update(
        PHONE_HOST="parity-vm",
        PHONE_PORT="12225",
        SOURCE_DIRS="/test-music/library\n/test-music/downloads",
        PHONE_DEST_DIR="/var/tmp/leroy-parity-music/Music",
    )
    parameters[JOBS[2]].update(TARGET_HOST="parity-vm", TARGET_PORT="12225", CONFIGURE_FIREWALL=False)
    parameters[JOBS[3]].update(
        DEPLOY_HOST="parity-vm", DEPLOY_PORT="12225", GIT_CREDENTIALS_ID="", REGISTRY_CREDENTIALS_ID=""
    )
    for name, params in parameters.items():
        xml = ET.fromstring((ROOT / "test-results/nas-parity/jenkins-configs" / (name + ".xml")).read_text())
        xml.find("properties").clear()
        definitions = ET.SubElement(
            ET.SubElement(xml.find("properties"), "hudson.model.ParametersDefinitionProperty"),
            "parameterDefinitions",
        )
        for key, value in params.items():
            param = ET.SubElement(
                definitions,
                "hudson.model."
                + ("Boolean" if isinstance(value, bool) else "String")
                + "ParameterDefinition",
            )
            ET.SubElement(param, "name").text = key
            ET.SubElement(param, "defaultValue").text = (
                str(value).lower() if isinstance(value, bool) else str(value)
            )
        for triggers in xml.findall("triggers"):
            triggers.clear()
        file = LOCAL / "fixtures" / (name + ".xml")
        file.write_text(ET.tostring(xml, encoding="unicode"))
        upload_file(file, REMOTE + "/fixtures/" + file.name, CREDENTIALS)
    remote(f"""cd {REMOTE}
chmod 644 fixtures/operations-credentials.json fixtures/*bootstrap*.xml fixtures/music-library-sync-smartphone.xml fixtures/nikicas-hub-deploy.xml config/test-secrets/operations-known-hosts config/test-secrets/root-user config/test-secrets/hub-user config/test-secrets/paperless-user config/test-secrets/paperless-password config/test-secrets/app-admin-secret config/test-secrets/app-salt config/test-secrets/event-salt
tar -xf music-fixture.tar -C fixtures
chmod -R a+rX fixtures/test-music
""")
    groovy = """import com.cloudbees.plugins.credentials.*
import com.cloudbees.plugins.credentials.domains.Domain
import com.cloudbees.plugins.credentials.impl.UsernamePasswordCredentialsImpl
import com.cloudbees.jenkins.plugins.sshcredentials.impl.BasicSSHUserPrivateKey
import org.jenkinsci.plugins.plaincredentials.impl.StringCredentialsImpl
import hudson.util.Secret
import groovy.json.JsonSlurper
def values=new JsonSlurper().parse(new File('/fixtures/operations-credentials.json'))
def provider=SystemCredentialsProvider.getInstance()
def add={ item -> assert !provider.credentials.any { it.id == item.id }; provider.getStore().addCredentials(Domain.global(),item) }
add(new UsernamePasswordCredentialsImpl(CredentialsScope.GLOBAL,'paperless-api-user','Isolated comparison only',values['paperless-user'],values['paperless-password']))
for (entry in [['phone-music-sync-ssh','root','bootstrap'],['nikicas-hub-bootstrap-ssh','root','bootstrap'],['nikicas-hub-deploy-ssh','nikicas-hub-deploy','deploy']]) {
 def key=new File('/root/.ssh/parity-'+entry[2]).text
 add(new BasicSSHUserPrivateKey(CredentialsScope.GLOBAL,entry[0],entry[1],new BasicSSHUserPrivateKey.DirectEntryPrivateKeySource(key),'','Isolated VM only'))
}
for (entry in [['nikicas-hub-default-admin-login-secret','app-admin-secret'],['nikicas-hub-app-salt','app-salt'],['nikicas-hub-event-hash-salt','event-salt']]) {
 add(new StringCredentialsImpl(CredentialsScope.GLOBAL,entry[0],'Isolated comparison only',Secret.fromString(values[entry[1]])))
}
provider.save()
println('Operations test credentials installed')
"""
    response = jenkins_python(
        AUTH
        + "print(request('/scriptText',urllib.parse.urlencode({'script':"
        + repr(groovy)
        + "}).encode()).decode())\n"
    )
    if response.strip() != "Operations test credentials installed":
        raise RuntimeError("Test credential installation was not confirmed")
    jenkins_python("""from pathlib import Path
hosts=Path('/etc/hosts')
if ' parity-vm' not in hosts.read_text():
 with hosts.open('a') as stream:stream.write('\\n10.232.98.11 parity-vm\\n')
path=Path('/test-music')
if not path.exists():path.symlink_to('/fixtures/test-music',target_is_directory=True)
print('Owned Jenkins test endpoints configured')
""")
    config = LOCAL / "config/runner.toml"
    text = config.read_text()
    assert "[profiles.operations]" not in text
    text += """
[profiles.operations]
image = "leroy-job:nas-parity"
network = "leroy-jobs"
memory = "2g"
cpus = 2
docker = true
host_mappings = {controller = "10.232.98.10", parity-vm = "10.232.98.11"}
mounts = ["type=bind,source=/sources,target=/sources,readonly", "type=bind,source=/fixtures/test-music,target=/test-music,readonly"]
[profiles.operations.secrets.paperless]
PAPERLESS_API_USERNAME = "/test-secrets/paperless-user"
PAPERLESS_API_PASSWORD = "/test-secrets/paperless-password"
[profiles.operations.secrets."music-ssh"]
SSH_KEY_FILE = "/test-secrets/bootstrap"
SSH_USER = "/test-secrets/root-user"
KNOWN_HOSTS = "/test-secrets/operations-known-hosts"
[profiles.operations.secrets."hub-bootstrap"]
BOOTSTRAP_SSH_KEY_FILE = "/test-secrets/bootstrap"
BOOTSTRAP_USER = "/test-secrets/root-user"
KNOWN_HOSTS = "/test-secrets/operations-known-hosts"
[profiles.operations.secrets."hub-deploy"]
SSH_KEY_FILE = "/test-secrets/deploy"
DEPLOY_SSH_KEY_FILE = "/test-secrets/deploy"
DEPLOY_USER = "/test-secrets/hub-user"
KNOWN_HOSTS = "/test-secrets/operations-known-hosts"
[profiles.operations.secrets."hub-app"]
DEFAULT_ADMIN_LOGIN_SECRET = "/test-secrets/app-admin-secret"
APP_SALT = "/test-secrets/app-salt"
EVENT_HASH_SALT = "/test-secrets/event-salt"
"""
    config.write_text(text)
    upload_file(config, REMOTE + "/config/runner.toml", CREDENTIALS)
    with closing(client()) as api:
        installed = {p["id"]: p for p in api.get("/api/pipelines").json()}
        for name in JOBS:
            jenkins("configure", name)
            spec = installed[name]["spec"]
            spec.update(profile="operations", enabled=False)
            api.put("/api/pipelines/" + name, json=spec).raise_for_status()
            folder = ROOT / "test-results/nas-parity/aligned" / name
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "prepared.json").write_text(
                json.dumps({"parameters": parameters[name], "job_started": False}, indent=2) + "\n"
            )
    marker.write_text(json.dumps({"jobs": JOBS, "runner_activation_pending": True}, indent=2) + "\n")
    print("Operations jobs prepared; activate the runner only after the current comparison finishes.")


if __name__ == "__main__":
    main()

"""Prepare a comparison job and separate test credentials, without starting it."""

import json
import secrets
import xml.etree.ElementTree as ET
from contextlib import closing

from compare_nas_antares import client, jenkins, jenkins_python
from deploy_nas_parity import CREDENTIALS, LOCAL, REMOTE, remote
from nas_ssh import ROOT, upload_file

PARAMETERS = {
    "GITEA_URL": "http://gitea:3000",
    "GITEA_CONTAINER_NAME": "gitea",
    "ENSURE_GITEA_ADMIN_LOGIN": True,
    "GITEA_ADMIN_EMAIL": "admin@leroy.test",
    "GITEA_OWNER": "gitea-admin",
    "GITEA_REPO": "home-lab-service-collection",
    "GITEA_REPO_PRIVATE": True,
    "GITEA_DEFAULT_BRANCH": "master",
    "GITEA_WAIT_SECONDS": "60",
    "GITEA_CREDENTIALS_ID": "gitea-http",
}

AUTH = """import base64,http.cookiejar,json,os,urllib.request,urllib.parse
opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
headers={'Authorization':'Basic '+base64.b64encode(('admin:'+os.environ['PARITY_PASSWORD']).encode()).decode()}
def request(path,data=None):
 with opener.open(urllib.request.Request('http://127.0.0.1:8080'+path,headers=headers,data=data),timeout=30) as r:
  return r.read()
crumb=json.loads(request('/crumbIssuer/api/json'));headers[crumb['crumbRequestField']]=crumb['crumb']
"""


def main():
    output = ROOT / "test-results/nas-parity/aligned/gitea-bootstrap-repo"
    output.mkdir(parents=True, exist_ok=True)
    marker = output / "prepared.json"
    if marker.exists():
        raise RuntimeError("Comparison job already prepared; no implicit replacement")
    private = LOCAL / "config/test-secrets"
    for name, value in {"gitea-user": "gitea-admin", "gitea-password": secrets.token_urlsafe(32)}.items():
        path = private / name
        if not path.exists():
            path.write_text(value, encoding="utf-8")
        upload_file(path, REMOTE + "/config/test-secrets/" + name, CREDENTIALS)
    credential = LOCAL / "fixtures/gitea-test-credential.json"
    credential.write_text(
        json.dumps({n: (private / ("gitea-" + n)).read_text() for n in ("user", "password")})
    )
    upload_file(credential, REMOTE + "/fixtures/" + credential.name, CREDENTIALS)
    original = ET.fromstring(
        (ROOT / "test-results/nas-parity/jenkins-configs/gitea-bootstrap-repo.xml").read_text()
    )
    properties = original.find("properties")
    properties.clear()
    definitions = ET.SubElement(
        ET.SubElement(properties, "hudson.model.ParametersDefinitionProperty"), "parameterDefinitions"
    )
    for name, value in PARAMETERS.items():
        parameter = ET.SubElement(
            definitions,
            "hudson.model." + ("Boolean" if isinstance(value, bool) else "String") + "ParameterDefinition",
        )
        ET.SubElement(parameter, "name").text = name
        ET.SubElement(parameter, "defaultValue").text = (
            str(value).lower() if isinstance(value, bool) else value
        )
    fixture = LOCAL / "fixtures/gitea-bootstrap-repo.xml"
    fixture.write_text(ET.tostring(original, encoding="unicode"), encoding="utf-8")
    upload_file(fixture, REMOTE + "/fixtures/" + fixture.name, CREDENTIALS)
    config = LOCAL / "config/runner.toml"
    text = config.read_text()
    if "[profiles.gitea]" not in text:
        text += """
[profiles.gitea]
image = "leroy-job:nas-parity"
network = "leroy-jobs"
memory = "2g"
cpus = 2
docker = true
host_mappings = {controller = "10.232.98.10"}
mounts = ["type=bind,source=/test-secrets,target=/test-secrets,readonly"]
[profiles.gitea.secrets."gitea-admin"]
GITEA_ADMIN_USER = "/test-secrets/gitea-user"
GITEA_ADMIN_PASSWORD = "/test-secrets/gitea-password"
"""
        config.write_text(text)
    upload_file(config, REMOTE + "/config/runner.toml", CREDENTIALS)
    # The enclosing NAS directory is mode 0700. These generated test credentials
    # are readable only through explicit mounts in the owned test containers.
    remote(f"""cd {REMOTE}
chmod 644 fixtures/gitea-test-credential.json fixtures/gitea-bootstrap-repo.xml config/test-secrets/gitea-user config/test-secrets/gitea-password config/runner.toml
docker compose up -d --no-deps --force-recreate runner
""")
    groovy = """import com.cloudbees.plugins.credentials.*
import com.cloudbees.plugins.credentials.domains.Domain
import com.cloudbees.plugins.credentials.impl.UsernamePasswordCredentialsImpl
import groovy.json.JsonSlurper
def credentials=new JsonSlurper().parse(new File('/fixtures/gitea-test-credential.json'))
def provider=SystemCredentialsProvider.getInstance()
assert !provider.credentials.any { it.id == 'gitea-http' }
provider.getStore().addCredentials(Domain.global(),new UsernamePasswordCredentialsImpl(CredentialsScope.GLOBAL,'gitea-http','Isolated comparison only',credentials.user,credentials.password))
provider.save()
println('Test credential installed')
"""
    response = jenkins_python(
        AUTH
        + "print(request('/scriptText',urllib.parse.urlencode({'script':"
        + repr(groovy)
        + "}).encode()).decode())\n"
    )
    if response.strip() != "Test credential installed":
        raise RuntimeError("Test credential installation was not confirmed")
    jenkins("configure", "gitea-bootstrap-repo")
    with closing(client()) as api:
        spec = next(p["spec"] for p in api.get("/api/pipelines").json() if p["id"] == "gitea-bootstrap-repo")
        spec["profile"] = "gitea"
        spec["enabled"] = False
        spec["repository"] = ""
        api.put("/api/pipelines/gitea-bootstrap-repo", json=spec).raise_for_status()
    marker.write_text(json.dumps({"parameters": PARAMETERS, "job_started": False}, indent=2) + "\n")
    print("Gitea comparison prepared; target creation and both runs remain explicit.")


if __name__ == "__main__":
    main()

"""Prepare isolated Docker networking and an original-source Jenkins comparison job."""

import json
import xml.etree.ElementTree as ET

from deploy_nas_parity import CREDENTIALS, LOCAL, REMOTE, remote
from nas_ssh import ROOT, upload_file


def main():
    fixtures = LOCAL / "fixtures"
    fixtures.mkdir(exist_ok=True)
    # Preserve the live SCM definition, replacing only the read-only repository,
    # immutable revision and automatic triggers. The Jenkinsfile is untouched.
    root = ET.fromstring((ROOT / "test-results/nas-parity/jenkins-configs/antares-ci.xml").read_text())
    root.find("properties").clear()
    root.find(".//userRemoteConfigs/hudson.plugins.git.UserRemoteConfig/url").text = "/sources/antares"
    baseline = json.loads((ROOT / "test-results/nas-parity/baseline.json").read_text())
    # The read-only mirror pins master; lightweight checkout interprets a SHA as a branch.
    assert baseline["sources"]["antares"]["commit"] == "ab245279a2c5ba85dedef1180e7fd63b7f5b1398"
    root.find(".//branches/hudson.plugins.git.BranchSpec/name").text = "*/master"
    (fixtures / "antares-ci.xml").write_text(ET.tostring(root, encoding="unicode"), encoding="utf-8")
    (fixtures / "jenkins.yaml").write_text(
        """jenkins:
  systemMessage: "Isolierter Leroy-NAS-Vergleich"
  numExecutors: 1
  mode: NORMAL
  securityRealm:
    local:
      allowsSignup: false
      users:
        - id: "admin"
          password: "${PARITY_PASSWORD}"
  authorizationStrategy:
    loggedInUsersCanDoAnything:
      allowAnonymousRead: false
""",
        encoding="utf-8",
    )
    (fixtures / "jenkins.env").write_text(
        "PARITY_PASSWORD=" + (LOCAL / "config/jenkins_password").read_text() + "\n", encoding="utf-8"
    )
    (fixtures / "parity.groovy").write_text(
        """import jenkins.model.Jenkins
def server = Jenkins.get()
if (server.getItem("antares-ci") == null) {
  new File("/fixtures/antares-ci.xml").withInputStream {
    server.createProjectFromXML("antares-ci", it)
  }
}
server.setNumExecutors(1)
server.save()
""",
        encoding="utf-8",
    )
    # Update only these owned configuration files; no production Docker networks.
    for name in ("compose.yaml", "dind.sh"):
        upload_file(ROOT / "infra/nas" / name, REMOTE + "/" + name, CREDENTIALS)
    for path in fixtures.iterdir():
        upload_file(path, REMOTE + "/fixtures/" + path.name, CREDENTIALS)
    remote(
        f"""cd {REMOTE}
    chmod 644 fixtures/jenkins.yaml fixtures/parity.groovy fixtures/antares-ci.xml dind.sh
    docker compose up -d --wait --wait-timeout 180
    docker exec leroy-nas-parity-docker-1 docker network inspect leroy-jobs >/dev/null 2>&1 ||
      docker exec leroy-nas-parity-docker-1 docker network create --subnet 10.234.98.0/24 --ip-range 10.234.98.128/25 leroy-jobs
    docker save leroy-job:nas-parity postgres:18.4-alpine3.24 | docker exec -i leroy-nas-parity-docker-1 docker load
    docker exec leroy-nas-parity-docker-1 docker run --rm leroy-job:nas-parity python -c 'import leroy.worker; print("Worker runtime import OK")'
    docker exec leroy-nas-parity-docker-1 docker run --rm --entrypoint sh \
      -v jenkins-parity-home:/parity-home leroy-job:nas-parity -c 'chown -R 0:0 /parity-home'
    docker exec leroy-nas-parity-docker-1 docker create --name jenkins-parity \
      --label io.leroy.nas-parity=true --init --network leroy-jobs --memory 2g --cpus 2 \
      --cap-drop ALL --security-opt no-new-privileges:true \
      --env-file /fixtures/jenkins.env \
      -e CASC_JENKINS_CONFIG=/fixtures/jenkins.yaml \
      -e 'JAVA_OPTS=-Xms128m -Xmx512m -Djenkins.install.runSetupWizard=false -Dhudson.plugins.git.GitSCM.ALLOW_LOCAL_CHECKOUT=true' \
      -v jenkins-parity-home:/var/jenkins_home -v /var/run/docker.sock:/var/run/docker.sock \
      -v /sources:/sources:ro -v /fixtures:/fixtures:ro \
      -v /fixtures/parity.groovy:/usr/share/jenkins/ref/init.groovy.d/parity.groovy:ro \
      --entrypoint /usr/local/bin/jenkins.sh leroy-job:nas-parity
    docker exec leroy-nas-parity-docker-1 docker start jenkins-parity
    """,
        timeout=900,
    )


if __name__ == "__main__":
    main()

"""Freeze live Jenkins plugins and Python for the isolated comparison only."""

import json
import xml.etree.ElementTree as ET

from compare_nas_antares import jenkins
from deploy_nas_parity import CREDENTIALS, LOCAL, REMOTE, remote
from nas_ssh import ROOT, upload_file


def main():
    for job in ("antares-ci", "home-lab-ci", "nikicas-hub-ci"):
        build = jenkins("status", job)["build"]
        if build["building"]:
            raise RuntimeError("Wait for the owned comparison build to finish: " + job)
    manifest = json.loads((ROOT / "test-results/nas-parity/jenkins-versions.json").read_text())
    assert all(p["active"] for p in manifest["production"]["plugins"])
    names = sorted(p["shortName"] for p in manifest["production"]["plugins"])
    exporter = LOCAL / "export-plugins.py"
    exporter.write_text(
        """import pathlib,sys,tarfile
root=pathlib.Path('/var/jenkins_home/plugins')
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as archive:
 for name in NAMES:
  path=root/(name+'.jpi')
  if not path.is_file() or path.is_symlink():raise ValueError('Expected a regular installed plugin file')
  archive.add(path,arcname=name+'.jpi',recursive=False)
""".replace("NAMES", repr(names)),
        encoding="utf-8",
    )
    upload_file(exporter, REMOTE + "/export-plugins.py", CREDENTIALS)
    upload_file(ROOT / "infra/nas/Dockerfile.parity", REMOTE + "/Dockerfile.parity", CREDENTIALS)
    # Match the recorded successful baseline already present in Leroy. This is
    # job configuration, not a change to the repository or its Jenkinsfile.
    home = LOCAL / "fixtures/home-lab-ci.xml"
    xml = ET.fromstring(home.read_text())
    parameters = xml.find(".//parameterDefinitions")
    previous = ET.SubElement(parameters, "hudson.model.StringParameterDefinition")
    ET.SubElement(previous, "name").text = "GIT_PREVIOUS_SUCCESSFUL_COMMIT"
    ET.SubElement(previous, "defaultValue").text = "9fb528a1bb4b736d53d294510b374d516e973a03"
    home.write_text(ET.tostring(xml, encoding="unicode"), encoding="utf-8")
    upload_file(home, REMOTE + "/fixtures/home-lab-ci.xml", CREDENTIALS)
    groovy = LOCAL / "fixtures/parity.groovy"
    groovy.write_text(
        """import jenkins.model.Jenkins
def server=Jenkins.get()
for (name in ["antares-ci", "home-lab-ci", "nikicas-hub-ci"]) {
  if (server.getItem(name)==null) {
    new File("/fixtures/"+name+".xml").withInputStream { server.createProjectFromXML(name,it) }
  }
}
server.setNumExecutors(2)
server.save()
""",
        encoding="utf-8",
    )
    upload_file(groovy, REMOTE + "/fixtures/parity.groovy", CREDENTIALS)
    remote(
        f"""cd {REMOTE}
    if docker exec leroy-nas-parity-docker-1 docker inspect jenkins-parity-initial >/dev/null 2>&1; then
      echo 'An aligned comparison was already provisioned; refusing an implicit replacement' >&2; exit 1
    fi
    docker exec -i jenkins python3 - < export-plugins.py > live-plugins.tar
    chmod 644 fixtures/parity.groovy fixtures/home-lab-ci.xml
    docker build --build-arg JENKINS_IMAGE=leroy-jenkins-base:nas-parity -f Dockerfile.parity -t leroy-job:nas-parity .
    docker save leroy-job:nas-parity | docker exec -i leroy-nas-parity-docker-1 docker load
    docker exec leroy-nas-parity-docker-1 docker stop jenkins-parity
    docker exec leroy-nas-parity-docker-1 docker rename jenkins-parity jenkins-parity-initial
    docker exec leroy-nas-parity-docker-1 docker run --rm --entrypoint sh \
      -v jenkins-parity-aligned-home:/parity-home leroy-job:nas-parity \
      -c 'chown 0:0 /parity-home; mkdir -p /parity-home/plugins'
    docker exec -i leroy-nas-parity-docker-1 docker run --rm -i --entrypoint tar \
      -v jenkins-parity-aligned-home:/parity-home leroy-job:nas-parity \
      --no-same-owner -xf - -C /parity-home/plugins < live-plugins.tar
    docker exec leroy-nas-parity-docker-1 docker run --rm --entrypoint sh \
      -v jenkins-parity-aligned-home:/parity-home leroy-job:nas-parity \
      -c 'for file in /parity-home/plugins/*.jpi; do touch "$file.pinned"; done'
    docker exec leroy-nas-parity-docker-1 docker create --name jenkins-parity \
      --label io.leroy.nas-parity=true --init --network leroy-jobs --memory 2g --cpus 2 \
      --pids-limit 1024 --cap-drop ALL --security-opt no-new-privileges:true \
      --env-file /fixtures/jenkins.env -e CASC_JENKINS_CONFIG=/fixtures/jenkins.yaml \
      -e PLUGINS_FORCE_UPGRADE=false -e TRY_UPGRADE_IF_NO_MARKER=false \
      -e 'JAVA_OPTS=-Xms128m -Xmx512m -Djenkins.install.runSetupWizard=false -Dhudson.plugins.git.GitSCM.ALLOW_LOCAL_CHECKOUT=true' \
      -v jenkins-parity-aligned-home:/var/jenkins_home -v /var/run/docker.sock:/var/run/docker.sock \
      -v /sources:/sources:ro -v /fixtures:/fixtures:ro \
      -v /fixtures/parity.groovy:/usr/share/jenkins/ref/init.groovy.d/parity.groovy:ro \
      --entrypoint /usr/local/bin/jenkins.sh leroy-job:nas-parity
    docker exec leroy-nas-parity-docker-1 docker start jenkins-parity
    """,
        timeout=900,
    )


if __name__ == "__main__":
    main()

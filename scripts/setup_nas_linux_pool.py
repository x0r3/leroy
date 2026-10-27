"""Provision a bounded Linux execution pool attached to the NAS test controller.

Exports only the owned comparison images/plugins, never production credentials.
No public ports or production jobs are changed.
"""

import argparse
import hashlib
import json
import shlex
import shutil
import subprocess
import tarfile
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from nas_followup_support import inner, production_jobs
from nas_ssh import ROOT, connection

COMMIT = "58da3ef5d112f58bc0a3d1cbd75179eb71d421c1"
LOCAL = ROOT / ".local/nas-linux-pool"
EVIDENCE = ROOT / "test-results/nas-parity/followup/linux-pool"
PARENT = "leroy-nas-linux-pool"
INNER_IMAGES = {
    "leroy-job:nas-parity": "sha256:b3dd298d3eb60b978ad4847edab4730035993930f4b6d780a0106ef40de6017c",
    "leroy-job:nas-parity-before-lease-fix": "sha256:7036632df5ae7dd01cc050c3c89167fb05228aea6a840ac7a1d39de4babe49e4",
    "postgres:18.4-alpine3.24": "sha256:318a05a0be31793aa40b23c15fa633ae05610734fe07b304e144ea467d3c61b3",
    "mcr.microsoft.com/playwright:v1.61.1-noble": "sha256:5b8f294aff9041b7191c34a4bab3ac270157a28774d4b0660e9743297b697e48",
}


def docker(*args, timeout=60, **kwargs):
    kwargs.setdefault("check", True)
    return subprocess.run(["docker", *map(str, args)], capture_output=True, timeout=timeout, **kwargs)


def nested(*args, **kwargs):
    return docker("exec", PARENT, "docker", *args, **kwargs)


def download(name, command, timeout=900):
    """Pinned SSH, private askpass, binary stdout written directly to disk."""
    path = LOCAL / name
    marker = EVIDENCE / (name + ".json")
    if marker.exists():
        record = json.loads(marker.read_text())
        with path.open("rb") as stream:
            assert hashlib.file_digest(stream, "sha256").hexdigest() == record["sha256"]
        return record
    assert not path.exists(), "Retain interrupted exports separately before retrying"
    settings, args, env = connection(ROOT / ".local/nas-ssh.json")
    with path.open("wb") as stream:
        result = subprocess.run([*args, settings["username"] + "@" + settings["host"], command],
                                stdout=stream, stderr=subprocess.PIPE, env=env, timeout=timeout)
    assert result.returncode == 0, "Owned fixture export failed; credentials remain private"
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    record = {"name": name, "bytes": path.stat().st_size, "sha256": digest,
              "source": "owned NAS comparison stack", "production_read_only": True}
    marker.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record), flush=True)
    return record


def export():
    names = inner("ps", "--format", "{{.Names}}", timeout=60).splitlines()
    assert not any(n.startswith(("antares-", "leroy-")) for n in names)
    assert not json.loads(inner("inspect", "jenkins-parity", "--format", "{{json .State.Running}}"))
    actual = json.loads(inner("image", "inspect", *INNER_IMAGES))
    assert {r["RepoTags"][0]: r["Id"] for r in actual} == INNER_IMAGES
    download("job-images.tar", "docker exec leroy-nas-parity-docker-1 docker save " + shlex.join(INNER_IMAGES))
    download("supervisor-images.tar", "docker save leroy-runner:nas-parity docker:29.6.2-dind")
    download("plugins.tar", "docker exec leroy-nas-parity-docker-1 docker run --rm "
             "--label io.leroy.nas-parity=true --memory 128m --cpus 0.5 --volumes-from jenkins-parity "
             "--entrypoint sh leroy-job:nas-parity -c "
             + shlex.quote("cd /var/jenkins_home/plugins && tar -cf - *.jpi *.jpi.pinned"))
    download("tools.tar", "tar -cf - -C /volume1/docker/leroy-nas-parity/fixtures/graphato-tools/docker-config cli-plugins")
    (EVIDENCE / "export-production-jobs.json").write_text(json.dumps(production_jobs(), indent=2) + "\n")


def setup(resume=False):
    marker = EVIDENCE / "pool.json"
    assert not marker.exists(), "No implicit pool replacement"
    assert not json.loads(docker("inspect", "leroy-nas-target-vm", text=True).stdout)[0]["State"]["Running"]
    docker("load", "--input", LOCAL / "supervisor-images.tar", timeout=180)
    supervisors = json.loads(docker("image", "inspect", "leroy-runner:nas-parity", "docker:29.6.2-dind", text=True).stdout)
    # Docker Desktop's containerd store reports a manifest ID; the NAS classic
    # store reports the config ID. Verify actual config bytes and layer content.
    with tarfile.open(LOCAL / "supervisor-images.tar") as archive:
        exported = json.load(archive.extractfile("manifest.json"))
        configurations = {}
        for row in exported:
            data = archive.extractfile(row["Config"]).read()
            tag = row["RepoTags"][0]
            config = json.loads(data)
            actual = next(info for info in supervisors if tag in info["RepoTags"])
            assert actual["RootFS"]["Layers"] == config["rootfs"]["diff_ids"]
            assert all(actual["Config"].get(key) == value for key, value in config["config"].items())
            configurations[tag] = "sha256:" + hashlib.sha256(data).hexdigest()
    assert configurations["leroy-runner:nas-parity"] == "sha256:a8bec2e958bc488d050ed409228bb29478471a8898caabff4b8867d9f057e410"
    fixtures = LOCAL / "fixtures"
    fixtures.mkdir(exist_ok=True)
    sources = LOCAL / "sources/gitea-admin"
    sources.mkdir(parents=True, exist_ok=True)
    repo = sources / ("antares-candidate-" + COMMIT[:12] + ".git")
    if repo.exists():
        assert resume, "Never replace an existing source mirror"
        assert subprocess.check_output(["git", "--git-dir", str(repo), "rev-parse", "refs/heads/master"], text=True).strip() == COMMIT
    else:
        assert not resume
        subprocess.run(["git", "clone", "--bare", "--no-hardlinks", str(ROOT / ".sources/antares-capture-validation"), str(repo)], check=True, capture_output=True, timeout=90)
    for args in [("update-ref", "refs/heads/master", COMMIT), ("symbolic-ref", "HEAD", "refs/heads/master"), ("update-server-info",)]:
        subprocess.run(["git", "--git-dir", str(repo), *args], check=True, capture_output=True)
    source = "http://gitea:3000/gitea-admin/" + repo.name
    xml = ET.fromstring((ROOT / ".local/nas-parity/fixtures/antares-ci.xml").read_text())
    xml.find(".//hudson.plugins.git.UserRemoteConfig/url").text = source
    xml.find("properties").clear()
    (fixtures / "antares-ci.xml").write_text(ET.tostring(xml, encoding="unicode"))
    shutil.copyfile(ROOT / ".local/nas-parity/fixtures/jenkins.env", fixtures / "jenkins.env")
    (fixtures / "parity.groovy").write_text('''import jenkins.model.Jenkins
def server=Jenkins.get()
if (server.getItem("antares-ci")==null) {
  new File("/fixtures/antares-ci.xml").withInputStream { server.createProjectFromXML("antares-ci",it) }
}
server.setNumExecutors(2)
server.save()
''', newline="\n")
    yaml = (ROOT / ".local/nas-parity/fixtures/jenkins.yaml").read_text()
    yaml += '  globalNodeProperties:\n    - envVars:\n        env:\n          - key: "LEROY_TEST_POOL"\n            value: "linux"\n'
    (fixtures / "jenkins.yaml").write_text(yaml)
    policy = (ROOT / "infra/nas/antares-docker.py").read_text()
    (fixtures / "antares-docker.py").write_text(policy, newline="\n")
    (LOCAL / "dind.sh").write_text('''#!/bin/sh
set -eu
rm -f /run/leroy-isolation-ready
dockerd-entrypoint.sh "$@" &
daemon=$!
trap 'kill -TERM "$daemon"; wait "$daemon" || true' TERM INT
attempts=0
until docker info >/dev/null 2>&1; do
 attempts=$((attempts + 1))
 [ "$attempts" -lt 90 ] && kill -0 "$daemon" || exit 1
 sleep 1
done
iptables -N LEROY-POOL-EGRESS
iptables -A LEROY-POOL-EGRESS -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
iptables -A LEROY-POOL-EGRESS -d 10.237.98.0/24 -j RETURN
iptables -A LEROY-POOL-EGRESS -d 10.238.0.0/16 -j RETURN
iptables -A LEROY-POOL-EGRESS -d 192.168.178.97 -p tcp --dport 8088 -j RETURN
# Docker Desktop's private DNS forwarder; no other host port is permitted.
iptables -A LEROY-POOL-EGRESS -d 192.168.65.7 -p udp --dport 53 -j RETURN
iptables -A LEROY-POOL-EGRESS -d 192.168.65.7 -p tcp --dport 53 -j RETURN
for destination in 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 169.254.0.0/16 87.106.133.233/32 213.165.73.233/32; do
 iptables -A LEROY-POOL-EGRESS -d "$destination" -j REJECT
done
iptables -A LEROY-POOL-EGRESS -j RETURN
iptables -I DOCKER-USER 1 -j LEROY-POOL-EGRESS
iptables -I OUTPUT 1 -j LEROY-POOL-EGRESS
touch /run/leroy-isolation-ready
wait "$daemon"
''', newline="\n")
    existing = docker("inspect", PARENT, check=False, text=True)
    if existing.returncode == 0:
        assert resume, "No implicit existing-pool reuse"
        info = json.loads(existing.stdout)[0]
        assert info["Config"]["Labels"]["io.leroy.nas-linux-pool"] == "true"
        assert info["Config"]["Image"] == supervisors[1]["Id"]
        assert info["HostConfig"]["Memory"] == info["HostConfig"]["MemorySwap"] == 8*1024**3
        assert info["HostConfig"]["NanoCpus"] == 6_000_000_000 and not info["HostConfig"]["PortBindings"]
        assert not nested("ps", "-a", "-q", text=True).stdout.strip(), "Inspect an initialized pool explicitly"
    else:
        docker("create", "--name", PARENT, "--label", "io.leroy.nas-linux-pool=true", "--privileged",
           "--restart", "unless-stopped",
           "--memory", "8g", "--memory-swap", "8g", "--cpus", "6", "-e", "DOCKER_TLS_CERTDIR=",
           "-v", "leroy-nas-linux-pool-engine:/var/lib/docker", "-v", str(fixtures) + ":/fixtures:ro",
           "-v", str(LOCAL) + ":/pool-input:ro",
           "-v", str(LOCAL / "sources") + ":/sources:ro", "-v", str(LOCAL / "dind.sh") + ":/leroy-dind.sh:ro",
           "--entrypoint", "sh", supervisors[1]["Id"], "/leroy-dind.sh", "--bip=10.237.98.1/24",
           "--default-address-pool=base=10.238.0.0/16,size=24")
    docker("start", PARENT)
    for _ in range(60):
        if docker("exec", PARENT, "test", "-f", "/run/leroy-isolation-ready", check=False).returncode == 0:
            break
        time.sleep(1)
    else:
        raise TimeoutError("Linux pool isolation rules did not become ready")
    nested("load", "--input", "/pool-input/job-images.tar", timeout=300)
    actual = json.loads(nested("image", "inspect", *INNER_IMAGES, text=True).stdout)
    imported_images = {}
    image_config_ids = {}
    with tarfile.open(LOCAL / "job-images.tar") as archive:
        for row in json.load(archive.extractfile("manifest.json")):
            data = archive.extractfile(row["Config"]).read()
            tag = row["RepoTags"][0]
            image_config_ids[tag] = "sha256:" + hashlib.sha256(data).hexdigest()
            config = json.loads(data)
            imported = next(info for info in actual if tag in info["RepoTags"])
            assert imported["Id"] == INNER_IMAGES[tag]
            assert imported["RootFS"]["Layers"] == config["rootfs"]["diff_ids"]
            assert all(imported["Config"].get(key) == value for key, value in config["config"].items())
            imported_images[tag] = imported["Id"]
    nested("network", "create", "--subnet", "10.238.98.0/24", "leroy-jobs")
    for name, directory in (("tools.tar", "/fixtures-tools"), ("plugins.tar", "/plugins-import")):
        docker("exec", PARENT, "mkdir", "-p", directory)
        docker("exec", PARENT, "tar", "-xf", "/pool-input/" + name, "-C", directory)
    nested("run", "--rm", "--entrypoint", "sh", "-v", "jenkins-parity-aligned-home:/var/jenkins_home",
           "-v", "/plugins-import:/plugins-import:ro", "leroy-job:nas-parity",
           "-c", "chown 0:0 /var/jenkins_home && mkdir -p /var/jenkins_home/plugins && cp /plugins-import/* /var/jenkins_home/plugins/")
    cid = nested("create", "--name", "jenkins-parity", "--label", "io.leroy.nas-linux-pool=true",
                 "--init", "--network", "leroy-jobs", "--memory", "2g", "--memory-swap", "4g", "--cpus", "2",
                 "--pids-limit", "1024", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
                 "--env-file", "/fixtures/jenkins.env", "-e", "CASC_JENKINS_CONFIG=/fixtures/jenkins.yaml",
                 "-e", "PLUGINS_FORCE_UPGRADE=false", "-e", "TRY_UPGRADE_IF_NO_MARKER=false", "-e", "LEROY_NAS_ANTARES_TMPFS=1",
                 "-e", "JAVA_OPTS=-Xms128m -Xmx512m -Djenkins.install.runSetupWizard=false -Dhudson.plugins.git.GitSCM.ALLOW_LOCAL_CHECKOUT=true",
                 "-v", "jenkins-parity-aligned-home:/var/jenkins_home", "-v", "/var/run/docker.sock:/var/run/docker.sock",
                 "-v", "/sources:/sources:ro", "-v", "/fixtures:/fixtures:ro",
                 "-v", "/fixtures-tools/cli-plugins:/usr/local/lib/docker/cli-plugins:ro",
                 "-v", "/fixtures/antares-docker.py:/usr/local/bin/docker:ro",
                 "-v", "/fixtures/parity.groovy:/usr/share/jenkins/ref/init.groovy.d/parity.groovy:ro",
                 "--entrypoint", "/usr/local/bin/jenkins.sh", "leroy-job:nas-parity-before-lease-fix", text=True).stdout.strip()
    policy = policy.replace('parent == "29e75d9173c9"', 'parent == ' + repr(cid[:12]))
    policy = policy.replace('parent == "29e75d9173c95db4f448ac038f2593e1f556e7eb2bf49bde68cba911526f3226"', 'parent == ' + repr(cid))
    (fixtures / "antares-docker.py").write_text(policy, newline="\n")
    nested("run", "-d", "--name", "gitea", "--label", "io.leroy.nas-linux-pool=true", "--network", "leroy-jobs",
           "--restart", "unless-stopped",
           "--memory", "128m", "--cpus", "0.5", "-v", "/sources:/sources:ro", "--entrypoint", "python3",
           "leroy-job:nas-parity", "-m", "http.server", "3000", "--directory", "/sources")
    config = '''capacity = 2
[profiles.antares-linux]
image = "leroy-job:nas-parity"
network = "leroy-jobs"
memory = "4g"
cpus = 6
docker = true
mounts = ["type=bind,source=/sources,target=/sources,readonly", "type=bind,source=/fixtures-tools/cli-plugins,target=/usr/local/lib/docker/cli-plugins,readonly", "type=bind,source=/fixtures/antares-docker.py,target=/usr/local/bin/docker,readonly"]
[profiles.antares-linux.environment]
NODE_OPTIONS = "--max-old-space-size=2048"
LEROY_NAS_ANTARES_TMPFS = "1"
'''
    (LOCAL / "runner.toml").write_text(config)
    docker("create", "--name", "leroy-nas-linux-runner", "--label", "io.leroy.nas-linux-pool=true", "--memory", "192m", "--cpus", "0.5",
           "--restart", "unless-stopped",
           "-v", str(LOCAL / "runner.toml") + ":/config/runner.toml:ro",
           "-v", str(ROOT / ".local/nas-parity/config/runner_token") + ":/run/secrets/runner_token:ro",
           "-e", "LEROY_CONTROLLER=http://192.168.178.97:8088", "-e", "DOCKER_HOST=tcp://127.0.0.1:2375",
           "-e", "LEROY_RUNNER_TOKEN_FILE=/run/secrets/runner_token", "-e", "LEROY_RUNNER_ID=runner-nas-linux-pool",
           "--network", "container:" + PARENT, supervisors[0]["Id"])
    docker("start", "leroy-nas-linux-runner")
    info = json.loads(docker("inspect", PARENT, text=True).stdout)[0]
    record = {"at": datetime.now(timezone.utc).isoformat(), "candidate": COMMIT,
              "controller": "http://192.168.178.97:8088", "execution_host": "Docker Desktop Linux VM on Windows",
              "parent": PARENT, "parent_id": info["Id"], "memory_bytes": info["HostConfig"]["Memory"],
              "memory_swap_bytes": info["HostConfig"]["MemorySwap"], "cpus": 6, "profile": "antares-linux",
              "jenkins_id": cid, "source": source, "image_config_ids": image_config_ids,
              "images": imported_images, "runner_image": supervisors[0]["Id"],
              "daemon_image": supervisors[1]["Id"], "policy_sha256": hashlib.sha256((fixtures / "antares-docker.py").read_bytes()).hexdigest(),
              "supervisor_image_config_ids": configurations,
              "source_service": "read-only Git HTTP fixture with frozen repository objects",
              "production_modified": False, "full_ci_acceptance": False}
    marker.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["export", "setup"])
    parser.add_argument("--resume-fixtures", action="store_true", help="Reuse verified frozen fixtures after retained setup failure")
    args = parser.parse_args()
    LOCAL.mkdir(exist_ok=True)
    EVIDENCE.mkdir(exist_ok=True)
    assert not args.resume_fixtures or args.phase == "setup"
    export() if args.phase == "export" else setup(args.resume_fixtures)


if __name__ == "__main__":
    main()

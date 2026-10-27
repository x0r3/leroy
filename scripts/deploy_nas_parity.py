"""Deploy only the owned, manual NAS comparison stack over authenticated SSH.

Production services are neither replaced nor connected to the test Docker daemon.
The initial runner can execute Antares only; other profiles remain unconfigured.
"""

import argparse
import hashlib
import json
import secrets
import subprocess
import tarfile

from nas_ssh import ROOT, run_script, upload_file

REMOTE = "/volume1/docker/leroy-nas-parity"
LOCAL = ROOT / ".local/nas-parity"
CREDENTIALS = ROOT / ".local/nas-ssh.json"


def remote(script, timeout=300):
    result = run_script("set -eu\n" + script, CREDENTIALS, timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stderr[-4000:])
    print(result.stdout[-4000:], flush=True)
    return result.stdout


def prepare():
    from leroy.catalog import catalog

    LOCAL.mkdir(parents=True, exist_ok=True)
    config = LOCAL / "config"
    config.mkdir(exist_ok=True)
    (config / "test-secrets").mkdir(exist_ok=True)
    for name in ("admin_password", "db_password", "runner_token", "jenkins_password"):
        path = config / name
        if not path.exists():
            path.write_text(secrets.token_urlsafe(36), encoding="utf-8")
    db_password = (config / "db_password").read_text()
    (config / "controller.env").write_text(
        f"LEROY_DATABASE_URL=postgresql+psycopg://leroy:{db_password}@postgres/leroy\n"
        "LEROY_ORIGIN=http://192.168.178.97:8088\nLEROY_COOKIE_SECURE=false\n",
        encoding="utf-8",
    )
    inventory = json.loads((ROOT / "test-results/nas-parity/baseline.json").read_text())
    migrated = {pipeline.id: pipeline for pipeline in catalog()}
    toml = ""
    for job in inventory["pipelines"]:
        name = job["pipeline"]
        toml += f'\n[pipelines."{name}"]\nenabled = false\nprofile = "'
        toml += 'antares"\n' if name == "antares-ci" else 'unconfigured"\n'
        # Inline Jenkins jobs can use supporting scripts from a repository in
        # Leroy. Their provenance label is not itself a checkout path.
        source = migrated[name].repository
        if source:
            repository_name = source.rsplit("/", 1)[-1].removesuffix(".git")
            toml += f'repository = "/sources/{repository_name}"\nref = "master"\n'
    (config / "leroy.toml").write_text(toml, encoding="utf-8")
    (config / "runner.toml").write_text(
        'capacity = 2\n[profiles.antares]\nimage = "leroy-job:nas-parity"\n'
        'network = "leroy-jobs"\nmemory = "2g"\ncpus = 2\ndocker = true\n'
        'host_mappings = {controller = "10.232.98.10"}\n'
        'mounts = ["type=bind,source=/sources,target=/sources,readonly"]\n',
        encoding="utf-8",
    )
    for name, source in inventory["sources"].items():
        repository = ROOT / source.get("local_checkout", ".sources/" + name)
        actual = subprocess.check_output(["git", "-C", str(repository), "rev-parse", "HEAD"]).decode().strip()
        if actual != source["commit"]:
            raise ValueError("Original source identity changed: " + name)
        bundle = LOCAL / (name + ".bundle")
        subprocess.run(["git", "-C", str(repository), "bundle", "create", str(bundle), "HEAD"], check=True)
    with tarfile.open(LOCAL / "configuration.tar.gz", "w:gz") as archive:
        archive.add(ROOT / "infra/nas/compose.yaml", "compose.yaml")
        archive.add(ROOT / "infra/nas/Dockerfile.parity", "Dockerfile.parity")
        archive.add(ROOT / "infra/nas/dind.sh", "dind.sh")
        archive.add(config, "config")
        archive.add(ROOT / "test-results/nas-parity/baseline.json", "baseline.json")
        for bundle in LOCAL.glob("*.bundle"):
            archive.add(bundle, "bundles/" + bundle.name)
    subprocess.run(["docker", "tag", "leroy-controller:local", "leroy-controller:nas-parity"], check=True)
    subprocess.run(
        [
            "docker",
            "image",
            "save",
            "-o",
            str(LOCAL / "images.tar"),
            "leroy-controller:nas-parity",
            "leroy-runner:nas-parity",
            "postgres:18.4-alpine3.24",
        ],
        check=True,
    )
    print("Prepared private configuration, unchanged Git bundles and images", flush=True)


def deploy():
    remote(f"""if [ -e {REMOTE} ] && [ ! -f {REMOTE}/.leroy-owned ]; then
      echo 'Refusing an existing directory without the ownership marker' >&2; exit 1
    fi
    mkdir -p {REMOTE}
    chmod 700 {REMOTE}
    touch {REMOTE}/.leroy-owned
    """)
    for name in ("configuration.tar.gz", "images.tar"):
        print("Transferring", name, flush=True)
        upload_file(LOCAL / name, REMOTE + "/" + name, CREDENTIALS, timeout=1800)
        expected = hashlib.file_digest((LOCAL / name).open("rb"), "sha256").hexdigest()
        remote(f"cd {REMOTE}\nprintf '%s  %s\\n' '{expected}' '{name}' | sha256sum -c -\n")
    remote(
        f"""cd {REMOTE}
    python3 - <<'PY'
import pathlib,tarfile
root=pathlib.Path.cwd()
with tarfile.open('configuration.tar.gz') as archive:
 for member in archive:
  target=(root/member.name).resolve()
  if not target.is_relative_to(root) or not (member.isfile() or member.isdir()):
   raise ValueError('Unsafe archive entry')
  if member.isdir(): target.mkdir(parents=True,exist_ok=True)
  else:
   target.parent.mkdir(parents=True,exist_ok=True)
   target.write_bytes(archive.extractfile(member).read())
   target.chmod(0o644)
(root/'config').chmod(0o700)
(root/'configuration.tar.gz').chmod(0o600)
PY
    mkdir -p sources fixtures config/test-secrets
    printf '*\\n!Dockerfile.parity\\n' > .dockerignore
    docker image load -i images.tar
    docker tag sha256:03daffe03ae4aa3d90256f10e04b635bf6b8f5e981f55f97f1115105ae4d230f leroy-jenkins-base:nas-parity
    docker build --build-arg JENKINS_IMAGE=leroy-jenkins-base:nas-parity -f Dockerfile.parity -t leroy-job:nas-parity .
    docker run --rm --entrypoint python -v "$PWD:/parity" leroy-job:nas-parity -c '
import json,pathlib,subprocess
root=pathlib.Path("/parity")
for name,source in json.loads((root/"baseline.json").read_text())["sources"].items():
 dest=root/"sources"/name
 if not dest.exists():
  subprocess.run(["git","init","--bare",str(dest)],check=True)
  subprocess.run(["git","-C",str(dest),"fetch",str(root/"bundles"/(name+".bundle")),"HEAD:refs/heads/master"],check=True)
  subprocess.run(["git","-C",str(dest),"symbolic-ref","HEAD","refs/heads/master"],check=True)
 actual=subprocess.check_output(["git","-C",str(dest),"rev-parse","HEAD"]).decode().strip()
 assert actual==source["commit"],name
 print(name,actual)
'
    docker compose config --quiet
    docker compose up -d --wait --wait-timeout 180
    docker compose ps --format json
    """,
        timeout=1200,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["prepare", "deploy"])
    args = parser.parse_args()
    {"prepare": prepare, "deploy": deploy}[args.phase]()


if __name__ == "__main__":
    main()

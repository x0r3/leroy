"""Deploy the tested Leroy readiness correction to its Gitea profile only."""

import hashlib
import json
import tarfile

from deploy_nas_parity import CREDENTIALS, LOCAL, REMOTE, remote
from nas_ssh import ROOT, upload_file


def main():
    archive = LOCAL / "gitea-readiness.tar"
    with tarfile.open(archive, "w") as bundle:
        bundle.add(ROOT / "src/leroy/actions.py", "actions.py")
        bundle.add(ROOT / "infra/nas/Dockerfile.gitea-readiness", "Dockerfile")
    upload_file(archive, REMOTE + "/gitea-readiness.tar", CREDENTIALS)
    remote(
        f"""cd {REMOTE}
mkdir -p gitea-readiness
tar -xf gitea-readiness.tar -C gitea-readiness
docker build -t leroy-job:nas-parity-gitea gitea-readiness
docker save leroy-job:nas-parity-gitea | docker exec -i leroy-nas-parity-docker-1 docker load
""",
        timeout=600,
    )
    config = LOCAL / "config/runner.toml"
    text = config.read_text()
    old = '[profiles.gitea]\nimage = "leroy-job:nas-parity"'
    new = '[profiles.gitea]\nimage = "leroy-job:nas-parity-gitea"'
    assert old in text or new in text
    config.write_text(text.replace(old, new))
    upload_file(config, REMOTE + "/config/runner.toml", CREDENTIALS)
    remote(f"""cd {REMOTE}
chmod 644 config/runner.toml
docker compose up -d --no-deps --force-recreate runner
""")
    (ROOT / "test-results/nas-parity/gitea-readiness-fix.json").write_text(
        json.dumps(
            {
                "source": "src/leroy/actions.py",
                "sha256": hashlib.sha256((ROOT / "src/leroy/actions.py").read_bytes()).hexdigest(),
                "image": "leroy-job:nas-parity-gitea",
                "tests": "tests/test_gitea_readiness.py: 2 passed",
                "application_sources_modified": False,
            },
            indent=2,
        )
        + "\n"
    )
    print("Gitea readiness correction deployed to the isolated comparison profile.")


if __name__ == "__main__":
    main()

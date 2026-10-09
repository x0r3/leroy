"""Provision real services inside Leroy's dedicated nested Docker daemon only.

Run after compose.test.yaml. This script never contacts production deployment hosts.
Existing target containers and generated credentials are preserved.
"""

import json
import secrets
import subprocess
import time

from test_support import DIN, ROOT, inner

GITEA = "gitea/gitea:1.23.7"
REGISTRY = "registry:3.0.0"
PAPERLESS = "ghcr.io/paperless-ngx/paperless-ngx@sha256:5fa76604a81df6945086e0837b14b56543d137e8ce4f311cc5d9ebe907e74e79"
REDIS = "redis@sha256:858f009f9709ce576febc734aa78b8f6d624b82571f9ddb6bda4377c833b3499"


def ensure(name, image, *options):
    names = inner("ps", "-a", "--format", "{{.Names}}").splitlines()
    if name not in names:
        inner(
            "run",
            "-d",
            "--name",
            name,
            "--network",
            "leroy-jobs",
            "--label",
            "io.leroy.test-target=true",
            *options,
            image,
        )
    else:
        inner("start", name)
    print("Ready:", name, flush=True)


def write_secret(name, value):
    path = ROOT / ".local/test-secrets" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(value, encoding="utf-8")
    return path.read_text(encoding="utf-8").strip()


def main():
    if "leroy-jobs" not in inner("network", "ls", "--format", "{{.Name}}").splitlines():
        inner("network", "create", "leroy-jobs")
    ensure("registry", REGISTRY, "-p", "5000:5000")
    ip = inner("inspect", "--format", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", "registry")
    subprocess.run(["docker", "exec", DIN, "sh", "-c", f'echo "{ip} registry" >> /etc/hosts'], check=True)
    subprocess.run(["docker", "cp", str(ROOT / "tests/targets"), DIN + ":/test-targets"], check=True)
    inner("build", "-t", "leroy-test-host:local", "/test-targets")
    for name in ("music-target", "hub-target", "graphato-target"):
        ensure(
            name,
            "leroy-test-host:local",
            "--privileged",
            "--cgroupns=private",
            "--tmpfs",
            "/run",
            "--tmpfs",
            "/run/lock",
            "--tmpfs",
            "/tmp",
            "--mount",
            f"type=volume,source={name}-engine,target=/var/lib/docker",
            "--mount",
            f"type=volume,source={name}-containerd,target=/var/lib/containerd",
        )
    for key in ("bootstrap", "deploy", "music"):
        if not (ROOT / ".local/test-secrets" / key).exists():
            inner("exec", "music-target", "ssh-keygen", "-t", "ed25519", "-N", "", "-f", "/tmp/" + key)
            for suffix in ("", ".pub"):
                write_secret(
                    key + suffix, inner("exec", "music-target", "cat", "/tmp/" + key + suffix) + "\n"
                )
    known = []
    for name, key in (
        ("music-target", "music"),
        ("hub-target", "bootstrap"),
        ("graphato-target", "bootstrap"),
    ):
        pub = (ROOT / ".local/test-secrets" / (key + ".pub")).read_text(encoding="utf-8")
        # Preserve other authorized keys (including the forced Graphato deployment key).
        subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                DIN,
                "docker",
                "exec",
                "-i",
                name,
                "sh",
                "-c",
                "cat >> /root/.ssh/authorized_keys; sort -u /root/.ssh/authorized_keys -o /root/.ssh/authorized_keys; chmod 600 /root/.ssh/authorized_keys",
            ],
            input=pub,
            text=True,
            check=True,
        )
        known.append(name + " " + inner("exec", name, "cat", "/etc/ssh/ssh_host_ed25519_key.pub"))
    known_path = ROOT / ".local/test-secrets/known_hosts"
    if known_path.exists():
        # Preserve the separately pinned VM entry across idempotent target setup.
        known.extend(
            line
            for line in known_path.read_text(encoding="utf-8").splitlines()
            if line.startswith("[graphato-vm]:2222 ")
        )
    known_path.write_text("\n".join(known) + "\n", encoding="utf-8")
    inner("cp", "/sources/graphato/deployments/linux/host", "graphato-target:/root/leroy-host-scripts")
    inner("cp", "/test-secrets/deploy.pub", "graphato-target:/root/leroy-deploy.pub")
    inner(
        "exec",
        "graphato-target",
        "python3",
        "/root/leroy-host-scripts/ci-install.py",
        "--public-key",
        "/root/leroy-deploy.pub",
    )
    subprocess.run(["docker", "exec", DIN, "mkdir", "-p", "/leroy-releases"], check=True)
    subprocess.run(["docker", "exec", DIN, "chown", "1000:10", "/leroy-releases"], check=True)
    for name, value in {
        "gitea-user": "test-admin",
        "gitea-password": secrets.token_urlsafe(24),
        "paperless-user": "test-admin",
        "paperless-password": secrets.token_urlsafe(24),
        "root-user": "root",
        "hub-user": "nikicas-hub-deploy",
        "app-admin-secret": secrets.token_urlsafe(32),
        "app-salt": secrets.token_urlsafe(32),
        "event-salt": secrets.token_urlsafe(32),
    }.items():
        write_secret(name, value)
    ensure(
        "gitea-test",
        GITEA,
        "-e",
        "GITEA__security__INSTALL_LOCK=true",
        "-e",
        "GITEA__database__DB_TYPE=sqlite3",
        "-e",
        "GITEA__server__ROOT_URL=http://gitea-test:3000",
        "-e",
        "GITEA__service__DISABLE_REGISTRATION=true",
    )
    ensure("paperless-redis-test", REDIS)
    ensure(
        "paperless-test",
        PAPERLESS,
        "-e",
        "PAPERLESS_REDIS=redis://paperless-redis-test:6379",
        "-e",
        "PAPERLESS_ADMIN_USER=" + write_secret("paperless-user", "test-admin"),
        "-e",
        "PAPERLESS_ADMIN_PASSWORD=" + write_secret("paperless-password", secrets.token_urlsafe(24)),
        "-e",
        "PAPERLESS_SECRET_KEY=" + write_secret("app-salt", secrets.token_urlsafe(32)),
        "-e",
        "PAPERLESS_TIME_ZONE=Europe/Berlin",
        "-e",
        "PAPERLESS_URL=http://paperless-test:8000",
    )
    for _ in range(120):
        if inner("inspect", "--format", "{{.State.Health.Status}}", "paperless-test") == "healthy":
            break
        time.sleep(2)
    else:
        raise TimeoutError("Paperless target did not become healthy")
    print("Target services ready. Test secret paths are defined in examples/runner.test.toml.")
    images = json.loads(inner("image", "inspect", GITEA, REGISTRY, PAPERLESS, REDIS))
    (ROOT / "test-results").mkdir(exist_ok=True)
    (ROOT / "test-results/target-images.json").write_text(
        json.dumps(
            [{"id": image["Id"], "digests": image.get("RepoDigests", [])} for image in images], indent=2
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

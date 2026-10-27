"""Python implementations of the migrated stages; upstream workloads remain real."""

import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from .git_auth import git_environment


def run(*args, capture=False, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, text=True, capture_output=capture, **kwargs)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def required(name, values=None):
    value = (values or os.environ).get(name)
    if value is None or value == "":
        raise ValueError("Missing required setting: " + name)
    return str(value)


def ssh_args(host, user, port, identity, known_hosts):
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9.-]{0,252}", host):
        raise ValueError("Invalid SSH host")
    if not re.fullmatch(r"[a-z_][a-z0-9_-]*", user) or not 0 < int(port) < 65536:
        raise ValueError("Invalid SSH user or port")
    if not Path(identity).is_file() or not Path(known_hosts).is_file():
        raise ValueError("SSH identity and independently verified known_hosts are required")
    return [
        "ssh",
        "-i",
        identity,
        "-p",
        str(port),
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "UserKnownHostsFile=" + known_hosts,
        "-o",
        "ConnectTimeout=15",
        "-o",
        "ServerAliveInterval=15",
        "-o",
        "ServerAliveCountMax=3",
        user + "@" + host,
    ]


def checkout(c):
    spec, params = c["run"]["snapshot"], c["parameters"]
    repo = Path(c["repo"])
    source = params.get("GIT_URL") or spec["repository"]
    if not source:
        return {}
    ref = c["run"].get("commit") or params.get("RELEASE_COMMIT") or params.get("GIT_BRANCH") or spec["ref"]
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_./-]{0,199}", ref):
        raise ValueError("Invalid Git revision")
    with git_environment() as env:
        run("git", "clone", "--no-checkout", "--", source, repo, env=env)
    run("git", "checkout", "--detach", ref, cwd=repo)
    commit = run("git", "rev-parse", "HEAD", capture=True, cwd=repo).stdout.strip()
    print("Checked out immutable revision:", commit, flush=True)
    return {"commit": commit, "build_timestamp": datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")}


def inspect_images(c):
    commit = c["values"]["commit"]
    message = run("git", "log", "-1", "--pretty=%B", capture=True).stdout
    hub = c["run"]["pipeline_id"] == "nikicas-hub-ci"
    date = run(
        "git",
        "show",
        "-s",
        "--format=%cd",
        "--date=format-local:%Y%m%d",
        "HEAD",
        capture=True,
        env={**os.environ, "TZ": "Europe/Berlin"},
    ).stdout.strip()
    tag = commit[:12] + ("-" + date if hub else "")
    services = (
        [{"id": "nikicas-hub", "context": ".", "dockerfile": "Dockerfile"}]
        if hub
        else [
            {
                "id": "mail-ingest-service",
                "context": "mail-ingest-service",
                "dockerfile": "mail-ingest-service/Dockerfile",
            },
            {
                "id": "yt-downloader",
                "context": "yt-downloader/download-service",
                "dockerfile": "yt-downloader/download-service/Dockerfile",
            },
        ]
    )
    reason = ""
    base = c["run"].get("previous_successful_commit")
    if not hub:
        if (
            not base
            or subprocess.run(["git", "cat-file", "-e", base + "^{commit}"], capture_output=True).returncode
        ):
            candidate = subprocess.run(
                ["git", "rev-parse", "--verify", "HEAD~1"], capture_output=True, text=True
            )
            base = candidate.stdout.strip() if candidate.returncode == 0 else None
        if base:
            changed = run("git", "diff", "--name-only", base, commit, capture=True).stdout.splitlines()
            services = [
                s
                for s in services
                if any(
                    p == s["context"] or p == s["dockerfile"] or p.startswith(s["context"] + "/")
                    for p in changed
                )
            ]
    if "NO_CI" in message:
        reason = "Commit message contains NO_CI"
    elif not services:
        reason = "No service-relevant changes since the comparison revision"
    print("Build decision:", reason or ", ".join(s["id"] for s in services))
    return {
        "build_required": bool(services) and not reason,
        "services": services,
        "image_tag": tag,
        "build_date": date,
        "diff_base": base,
        "skip_reason": reason,
    }


def registry_login(registry):
    user, password = os.getenv("REGISTRY_USER"), os.getenv("REGISTRY_PASSWORD")
    if user and password:
        run("docker", "login", registry, "--username", user, "--password-stdin", input=password)
        return True
    return False


def build_images(c):
    registry = required("CI_REGISTRY_URL")
    namespace = os.getenv("CI_REGISTRY_NAMESPACE", "home-lab")
    logged_in = registry_login(registry)
    images = []
    try:
        for service in c["values"]["services"]:
            image = f"{registry}/{namespace}/{service['id']}"
            ref = image + ":" + c["values"]["image_tag"]
            command = [
                "docker",
                "build",
                "--pull",
                "--file",
                service["dockerfile"],
                "--tag",
                ref,
                "--tag",
                image + ":latest",
            ]
            if c["run"]["pipeline_id"] == "nikicas-hub-ci":
                for key, value in {
                    "BUILD_VERSION": c["values"]["image_tag"],
                    "BUILD_COMMIT": c["values"]["commit"],
                    "BUILD_DATE": c["values"]["build_date"],
                }.items():
                    command += ["--build-arg", key + "=" + value]
            run(*command, service["context"])
            run("docker", "push", ref)
            run("docker", "push", image + ":latest")
            inspection = json.loads(run("docker", "image", "inspect", ref, capture=True).stdout)[0]
            images.append(
                {"tag": ref, "image_id": inspection["Id"], "digests": inspection.get("RepoDigests", [])}
            )
    finally:
        if logged_in:
            run("docker", "logout", registry)
    (Path(c["results"]) / "images.json").write_text(json.dumps(images, indent=2))
    return {"images": images}


def toolchain(c):
    for command in [("node", "--version"), ("npm", "--version"), ("docker", "version")]:
        run(*command)
    return {}


def antares_database(c):
    name = "leroy-antares-" + c["run"]["id"]
    network = c["profile"].get("network", "leroy-jobs")
    run(
        "docker",
        "run",
        "-d",
        "--rm",
        "--name",
        name,
        "--label",
        "io.leroy.run=" + c["run"]["id"],
        "--network",
        network,
        "-e",
        "POSTGRES_DB=antares_test",
        "-e",
        "POSTGRES_USER=antares",
        "-e",
        "POSTGRES_PASSWORD=antares-test-password",
        "-e",
        "POSTGRES_INITDB_ARGS=--auth-host=scram-sha-256",
        "--health-cmd",
        "pg_isready -h 127.0.0.1 -U antares -d antares_test",
        "--health-interval",
        "2s",
        "--health-timeout",
        "3s",
        "--health-retries",
        "30",
        c["profile"].get("postgres_image", "postgres:18.4-alpine3.24"),
    )
    for _ in range(30):
        state = run(
            "docker", "inspect", "--format", "{{.State.Health.Status}}", name, capture=True
        ).stdout.strip()
        if state == "healthy":
            return {
                "database_container": name,
                "database_url": f"postgres://antares:antares-test-password@{name}:5432/antares_test",
            }
        time.sleep(2)
    raise TimeoutError("PostgreSQL did not become healthy")


def commands(c):
    for args in c["step"]["options"]["commands"]:
        if args == ["npm", "test"] and c["profile"].get("test_workers"):
            args = [*args, "--", "--maxWorkers=" + str(int(c["profile"]["test_workers"]))]
        run(*args)
    return {}


def antares_build(c):
    tag = "leroy/antares:" + c["run"]["id"]
    run("npm", "run", "build")
    run("docker", "compose", "config", "--quiet")
    run("docker", "build", "--tag", tag, ".")
    return {"image_tag": tag}


def antares_browsers(c):
    network = c["profile"].get("network", "leroy-jobs")
    run(
        "docker",
        "run",
        "--rm",
        "--init",
        "--label",
        "io.leroy.run=" + c["run"]["id"],
        "--ipc=host",
        "--network",
        network,
        "--volumes-from",
        os.environ["HOSTNAME"],
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--env",
        "CI=true",
        "--env",
        "HOME=/tmp",
        "--env",
        "TEST_DATABASE_URL=" + c["values"]["database_url"],
        "--env",
        "PLAYWRIGHT_BROWSERS_PATH=/ms-playwright",
        "--workdir",
        c["repo"],
        c["profile"].get("playwright_image", "mcr.microsoft.com/playwright:v1.61.1-noble"),
        "node",
        "node_modules/playwright/cli.js",
        "test",
    )
    return {}


def cleanup(c):
    containers = run(
        "docker", "ps", "-aq", "--filter", "label=io.leroy.run=" + c["run"]["id"], capture=True
    ).stdout.split()
    # Never remove the job container currently reporting its own cleanup.
    current = os.environ.get("HOSTNAME", "")
    for container in containers:
        if not (container.startswith(current) or current.startswith(container)):
            run("docker", "rm", "-f", "-v", container)
    if c["values"].get("image_tag", "").startswith("leroy/antares:"):
        run("docker", "image", "rm", c["values"]["image_tag"])
    return {}


def graphato_module(c):
    module = load(Path(c["repo"]) / "scripts/ci.py", "upstream_ci")
    config = c["profile"].get("graphato", {})
    module.STATE_ROOT = Path(c["work"]) / "graphato-ci"
    module.DESKTOP_RELEASES = required("desktop_releases", config)
    module.host_path = lambda path: str(
        Path(c["profile"].get("host_workspace", "/work")) / Path(path).resolve().relative_to(Path(c["work"]))
    )

    def builder():
        name = config.get("builder_name") or "leroy-graphato-" + c["run"]["id"]
        if not re.fullmatch(r"leroy-[a-z0-9-]+", name):
            raise ValueError("Builder name must stay in the Leroy-owned namespace")
        registry = required("GRAPHATO_REGISTRY_PUSH")
        module.STATE_ROOT.mkdir(exist_ok=True)
        cfg = module.STATE_ROOT / "buildkit.toml"
        cfg.write_text("[registry." + json.dumps(registry) + "]\n  http = true\n")
        if subprocess.run(["docker", "buildx", "inspect", name], capture_output=True).returncode:
            run(
                "docker",
                "buildx",
                "create",
                "--name",
                name,
                "--driver",
                "docker-container",
                "--buildkitd-config",
                cfg,
                "--driver-opt",
                "network=" + c["profile"].get("network", "leroy-jobs"),
                "--driver-opt",
                "image=moby/buildkit:v0.28.1",
                "--driver-opt",
                "memory=4g,memory-swap=6g,cpu-period=100000,cpu-quota=200000",
            )
        run("docker", "buildx", "inspect", "--bootstrap", name)
        os.environ["BUILDX_BUILDER"] = name
        return name

    module.builder = builder

    def transport():
        # Keep the checkout's validation and connection policy. The postdeploy
        # command, its run-bound cancellation and its report downloads each need
        # their own upstream connection, including after the first one fails.
        deployment = load(Path(c["repo"]) / "scripts/deploy-remote.py", "upstream_deployment")
        port = int(config.get("port", 22))
        if not 1 <= port <= 65535:
            raise ValueError("Invalid Graphato SSH port")
        args = SimpleNamespace(
            host=required("host", config),
            user=config.get("user", "root"),
            identity=Path(required("DEPLOY_KEY")),
            known_hosts=Path(required("KNOWN_HOSTS")),
        )
        return ["ssh", *deployment.ssh_options(args), "-o", f"Port={port}", f"{args.user}@{args.host}"]

    module.deployment_transport = transport
    return module


def graphato(c):
    cmd = c["step"]["options"]["command"]
    module = graphato_module(c)
    return graphato_action(c, module, cmd)


def graphato_action(c, module, cmd):
    work = Path(c["work"])
    bundle, desktop = work / "release", work / "desktop"
    commit = c["values"].get("commit") or c["parameters"].get("RELEASE_COMMIT")
    os.environ.update(
        {
            "RELEASE_COMMIT": commit,
            "GRAPHATO_BUILD_TIMESTAMP": c["values"]["build_timestamp"],
            "CI_STATE_FILE": str(work / "ci-state.json"),
            "WORKSPACE": c["repo"],
            "BUILD_NUMBER": str(c["run"]["number"]),
        }
    )
    if cmd == "release-needed":
        needed = module.release_needed(commit)
        return {
            "release_needed": needed,
            "skip_reason": "" if needed else "This immutable commit is already deployed",
        }
    if cmd == "basic-checks":
        module.basic_checks()
    elif cmd == "package":
        module.package(bundle)
        shutil.copy2(bundle / "manifest.json", Path(c["results"]) / "release-manifest.json")
        shutil.copy2(
            bundle.with_name(bundle.name + "-transfer.json"),
            Path(c["results"]) / "release-transfer-timings.json",
        )
    elif cmd == "package-desktop":
        module.package_desktop(desktop)
        shutil.copy2(desktop / "manifest.json", Path(c["results"]) / "desktop-release-manifest.json")
    elif cmd == "deploy":
        module.deploy(bundle)
        return {"delivery": "delivered", "acceptance": "pending"}
    elif cmd == "publish-desktop":
        module.publish_desktop(desktop)
    elif cmd == "postdeploy":
        suite = c["step"]["options"]["suite"]
        module.postdeploy(
            suite, commit, Path("target") / ("postdeploy-" + suite), c["parameters"].get("CHECK_GROUP", "all")
        )
    elif cmd == "release-status":
        receipt = module.release_status(commit, Path("release-status.json"))
        if (
            receipt["status"] != "verified"
            or c["values"].get("web_result") != "succeeded"
            or c["values"].get("quality_result") != "succeeded"
        ):
            raise ValueError(
                "Release acceptance incomplete; both full child suites and bound receipt are required"
            )
        return {"acceptance": "verified"}
    elif cmd == "cleanup":
        module.cleanup(Path(os.environ["CI_STATE_FILE"]))
        if not c["profile"].get("graphato", {}).get("builder_name"):
            subprocess.run(
                ["docker", "buildx", "rm", "leroy-graphato-" + c["run"]["id"]], capture_output=True
            )
    return {}


def current_master(c):
    source = c["run"]["snapshot"]["repository"]
    ref = c["run"]["snapshot"]["ref"]
    with git_environment() as env:
        head = run(
            "git", "ls-remote", "--", source, "refs/heads/" + ref, capture=True, env=env
        ).stdout.split()[0]
    matches = head == c["values"]["commit"]
    return {
        "is_current": matches,
        "skip_reason": "" if matches else "A newer branch revision exists; deployment suppressed",
    }


def graphato_source(c):
    cfg = c["profile"].get("graphato", {})
    source = required("repository", cfg)
    dest = Path(c["work"]) / "graphato-source"
    with git_environment() as env:
        run("git", "clone", "--no-checkout", "--", source, dest, env=env)
    run("git", "checkout", "--detach", c["parameters"].get("GRAPHATO_REF", "master"), cwd=dest)
    return {
        "graphato_source": str(dest),
        "bootstrap_commit": run("git", "rev-parse", "HEAD", capture=True, cwd=dest).stdout.strip(),
    }


def graphato_bootstrap(c):
    source = Path(c["values"]["graphato_source"])
    bootstrap = load(Path(c["repo"]) / "jenkins/graphato/run-bootstrap.py", "bootstrap")
    transport = load(source / "scripts/deploy-remote.py", "transport")
    original = bootstrap.settings

    def settings(source, environment):
        args = original(source, environment)
        args.known_hosts = Path(required("KNOWN_HOSTS"))
        return args

    bootstrap.settings = settings
    # Both ssh and scp accept -o Port, unlike their different short options.
    # Retain upstream identity/host-key validation for nonstandard SSH endpoints.
    original_ssh_options = transport.ssh_options
    port = int(c["profile"].get("graphato", {}).get("port", 22))
    if not 1 <= port <= 65535:
        raise ValueError("Invalid Graphato SSH port")
    transport.ssh_options = lambda args: [*original_ssh_options(args), "-o", f"Port={port}"]
    environment = {
        **os.environ,
        "BOOTSTRAP_HOST": required("TARGET_HOST", c["parameters"]),
        "BOOTSTRAP_DOMAIN": required("DOMAIN", c["parameters"]),
        "BOOTSTRAP_APPLY": str(c["parameters"].get("APPLY_CHANGES", False)).lower(),
    }
    bootstrap.execute(source, environment, transport)
    return {"mode": "apply" if c["parameters"].get("APPLY_CHANGES") else "inspect"}


def music_preflight(c):
    params = c["parameters"]
    sources = [
        s.strip() for s in required("SOURCE_DIRS", params).replace("\\n", "\n").splitlines() if s.strip()
    ]
    for source in sources:
        if not Path(source).is_dir():
            raise ValueError("Music source directory not mounted: " + source)
    ssh_args(
        required("PHONE_HOST", params),
        params.get("PHONE_USER") or required("SSH_USER"),
        params["PHONE_PORT"],
        required("SSH_KEY_FILE"),
        required("KNOWN_HOSTS"),
    )
    return {"sources": sources}


def music_sync(c):
    params = c["parameters"]
    exclude = Path(c["work"]) / "music-excludes.txt"
    exclude.write_text((params.get("EXCLUDE_PATTERNS") or "").replace("\\n", "\n"))
    args = [
        "python3",
        "jenkins/music-sync/music_sync.py",
        "--host",
        params["PHONE_HOST"],
        "--port",
        str(params["PHONE_PORT"]),
        "--user",
        params.get("PHONE_USER") or required("SSH_USER"),
        "--destination",
        params["PHONE_DEST_DIR"],
        "--ssh-key-file",
        required("SSH_KEY_FILE"),
        "--known-hosts-file",
        required("KNOWN_HOSTS"),
        "--timeout-seconds",
        str(params.get("TIMEOUT_SECONDS", 30)),
        "--exclude-file",
        str(exclude),
    ]
    for source in c["values"]["sources"]:
        args += ["--source", source]
    if params.get("DRY_RUN"):
        args += ["--dry-run"]
    run(*args)
    return {"sources_synced": len(c["values"]["sources"]), "dry_run": params.get("DRY_RUN", False)}


def paperless_preflight(c):
    required("PAPERLESS_API_URL", c["parameters"])
    rules = json.loads(Path("jenkins/paperless-bootstrap/default-rules.json").read_text())
    return {"rule_collections": list(rules)}


def paperless(c):
    params = c["parameters"]
    args = [
        "bash",
        "jenkins/paperless-bootstrap/bootstrap_rules.sh",
        "--base-url",
        params["PAPERLESS_API_URL"],
        "--rules-file",
        "jenkins/paperless-bootstrap/default-rules.json",
        "--timeout",
        str(params.get("TIMEOUT_SECONDS", 30)),
    ]
    if params.get("DRY_RUN"):
        args += ["--dry-run"]
    run(*args)
    return {"rules_applied": not params.get("DRY_RUN", False)}


def gitea_preflight(c):
    params = c["parameters"]
    if urllib.parse.urlsplit(required("GITEA_URL", params)).scheme not in ("http", "https"):
        raise ValueError("Gitea URL must use HTTP(S)")
    for name in ("GITEA_OWNER", "GITEA_REPO"):
        if not re.fullmatch(r"[a-zA-Z0-9_.-]+", required(name, params)):
            raise ValueError("Invalid " + name)
    run("docker", "inspect", "--format", "{{.State.Status}}", params["GITEA_CONTAINER_NAME"])
    return {}


def gitea_bootstrap(c):
    import base64

    params = c["parameters"]
    user, password = required("GITEA_ADMIN_USER"), required("GITEA_ADMIN_PASSWORD")
    container = required("GITEA_CONTAINER_NAME", params)
    if params.get("ENSURE_GITEA_ADMIN_LOGIN", True):
        command = ["docker", "exec", "--user", "git", container, "gitea", "admin", "user"]
        created = subprocess.run(
            [
                *command,
                "create",
                "--username",
                user,
                "--password",
                password,
                "--email",
                params["GITEA_ADMIN_EMAIL"],
                "--admin",
                "--must-change-password=false",
            ],
            capture_output=True,
            text=True,
        )
        if created.returncode:
            run(
                *command,
                "change-password",
                "--username",
                user,
                "--password",
                password,
                "--must-change-password=false",
            )
    base = params["GITEA_URL"].rstrip("/") + "/api/v1"
    # Jenkins waits after reconciling the admin account. A starting service must
    # not turn a recoverable readiness delay into a failed repository migration.
    deadline = time.monotonic() + int(params.get("GITEA_WAIT_SECONDS", 60))
    while (remaining := deadline - time.monotonic()) > 0:
        try:
            with urllib.request.urlopen(base + "/version", timeout=min(10, remaining)):
                break
        except (OSError, urllib.error.URLError):
            time.sleep(min(1, max(0, deadline - time.monotonic())))
    else:
        raise TimeoutError("Gitea API did not become ready within GITEA_WAIT_SECONDS")
    headers = {
        "Authorization": "Basic " + base64.b64encode((user + ":" + password).encode()).decode(),
        "Content-Type": "application/json",
    }

    def api(path, data=None):
        req = urllib.request.Request(
            base + path, data=json.dumps(data).encode() if data is not None else None, headers=headers
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as exc:
            return exc.code, None

    owner, repo = params["GITEA_OWNER"], params["GITEA_REPO"]
    status, result = api("/repos/" + owner + "/" + repo)
    if status == 200:
        return {"repository": owner + "/" + repo, "created": False}
    if status != 404:
        raise ValueError("Gitea repository lookup failed: HTTP " + str(status))
    if owner == user:
        path = "/user/repos"
    elif api("/orgs/" + owner)[0] == 200:
        path = "/orgs/" + owner + "/repos"
    elif api("/users/" + owner)[0] == 200:
        path = "/admin/users/" + owner + "/repos"
    else:
        raise ValueError("Repository owner does not exist")
    status, _ = api(
        path,
        {
            "name": repo,
            "private": params.get("GITEA_REPO_PRIVATE", True),
            "auto_init": False,
            "default_branch": params.get("GITEA_DEFAULT_BRANCH", "main"),
        },
    )
    if status not in (201, 409):
        raise ValueError("Gitea repository creation failed: HTTP " + str(status))
    return {"repository": owner + "/" + repo, "created": status == 201}


def hub_bootstrap_preflight(c):
    p = c["parameters"]
    user = p.get("BOOTSTRAP_USER") or required("BOOTSTRAP_USER")
    ssh_args(
        required("TARGET_HOST", p),
        user,
        p.get("TARGET_PORT", 22),
        required("BOOTSTRAP_SSH_KEY_FILE"),
        required("KNOWN_HOSTS"),
    )
    run("ansible-playbook", "--version")
    return {}


def hub_bootstrap(c):
    p = c["parameters"]
    inventory = Path(c["work"]) / "inventory.json"
    variables = Path(c["work"]) / "ansible-vars.json"
    key = run("ssh-keygen", "-y", "-f", required("DEPLOY_SSH_KEY_FILE"), capture=True).stdout.strip()
    inventory.write_text(
        json.dumps(
            {
                "all": {
                    "children": {
                        "nikicas_hub": {
                            "hosts": {
                                "target": {
                                    "ansible_host": p["TARGET_HOST"],
                                    "ansible_port": int(p.get("TARGET_PORT", 22)),
                                    "ansible_user": p.get("BOOTSTRAP_USER") or required("BOOTSTRAP_USER"),
                                    "ansible_ssh_private_key_file": required("BOOTSTRAP_SSH_KEY_FILE"),
                                    "ansible_ssh_common_args": "-o StrictHostKeyChecking=yes -o UserKnownHostsFile="
                                    + shlex.quote(required("KNOWN_HOSTS")),
                                }
                            }
                        }
                    }
                }
            }
        )
    )
    variables.write_text(
        json.dumps(
            {
                "nikicas_hub_deploy_public_key": key,
                "nikicas_hub_deploy_user": p.get("DEPLOY_USER") or required("DEPLOY_USER"),
                "nikicas_hub_deploy_dir": p["DEPLOY_DIR"],
                "nikicas_hub_domain": p["TRAEFIK_HOST_RULE"],
                "nikicas_hub_acme_storage_path": p["ACME_STORAGE_PATH"],
                "nikicas_hub_configure_firewall": p.get("CONFIGURE_FIREWALL", False),
                "nikicas_hub_ssh_port": str(p.get("TARGET_PORT", 22)),
                "nikicas_hub_runtime_uid": str(c["profile"].get("hub", {}).get("runtime_uid", 1000)),
            }
        )
    )
    args = [
        "ansible-playbook",
        "-i",
        str(inventory),
        "infra/nikicas-hub/bootstrap.yml",
        "--extra-vars",
        "@" + str(variables),
    ]
    if p.get("DRY_RUN"):
        args += ["--check", "--diff"]
    run(
        *args,
        env={
            **os.environ,
            "ANSIBLE_CONFIG": str(Path(c["repo"]) / "infra/nikicas-hub/ansible.cfg"),
            "ANSIBLE_HOST_KEY_CHECKING": "True",
        },
    )
    # The application image runs as UID 1000. A pre-existing host account may
    # give the deployment user a different UID; writable mounts must follow
    # the image identity instead of relying on coincidentally equal IDs.
    args[3] = str(Path(__file__).with_name("migrated") / "hub-runtime-permissions.yml")
    run(*args, env={**os.environ, "ANSIBLE_HOST_KEY_CHECKING": "True"})
    return {"mode": "check" if p.get("DRY_RUN") else "apply"}


def hub_deploy_preflight(c):
    p = c["parameters"]
    for name in (
        "DEPLOY_HOST",
        "DEPLOY_DIR",
        "ACME_STORAGE_PATH",
        "REGISTRY_URL",
        "REGISTRY_NAMESPACE",
        "IMAGE_NAME",
        "IMAGE_TAG",
    ):
        value = required(name, p)
        if not re.fullmatch(r"[a-zA-Z0-9_./:@-]+", value):
            raise ValueError("Unsafe value for " + name)
    if not Path("prod/docker-compose.yml").is_file():
        raise ValueError("Production compose definition missing")
    return {}


def hub_image(c):
    p = c["parameters"]
    image = f"{p['REGISTRY_URL']}/{p['REGISTRY_NAMESPACE']}/{p['IMAGE_NAME']}:{p['IMAGE_TAG']}"
    archive = Path(c["work"]) / ("nikicas-hub-" + p["IMAGE_TAG"] + ".tar")
    if not p.get("DRY_RUN"):
        logged = registry_login(p["REGISTRY_URL"])
        try:
            run("docker", "pull", image)
            run("docker", "save", "--output", archive, image)
        finally:
            if logged:
                run("docker", "logout", p["REGISTRY_URL"])
    return {"hub_image": image, "hub_archive": str(archive)}


def hub_deploy(c):
    p = c["parameters"]
    user = p.get("DEPLOY_USER") or required("DEPLOY_USER")
    ssh_args(
        p["DEPLOY_HOST"], user, p.get("DEPLOY_PORT", 22), required("SSH_KEY_FILE"), required("KNOWN_HOSTS")
    )
    env = {
        **os.environ,
        **{k: str(v).lower() if isinstance(v, bool) else str(v or "") for k, v in p.items()},
        "WORKSPACE": c["work"],
        "EFFECTIVE_DEPLOY_USER": user,
        "NIKICAS_HUB_IMAGE_REF": c["values"]["hub_image"],
        "NIKICAS_HUB_IMAGE_TAR": c["values"]["hub_archive"],
        "NIKICAS_HUB_IMAGE_TAG": p["IMAGE_TAG"],
    }
    run("bash", Path(__file__).with_name("migrated") / "hub-deploy.sh", env=env)
    return {"delivery": "validated" if p.get("DRY_RUN") else "delivered", "image": c["values"]["hub_image"]}


def demo(c):
    phase = c["step"]["options"]["phase"]
    if phase in ("unit", "lint"):
        for i in range(int(c["parameters"].get("SECONDS", 2))):
            print(f"{phase}: checking batch {i + 1}", flush=True)
            time.sleep(1)
    if phase == "unit" and c["parameters"].get("FAIL"):
        raise ValueError("Requested failure for execution validation")
    if phase == "package":
        Path("result.json").write_text(
            json.dumps({"run": c["run"]["id"], "checks": ["unit", "lint"], "passed": True})
        )
    print(f"{phase}: completed", flush=True)
    return {phase + "_complete": True}


ACTIONS = {
    f.__name__: f
    for f in [
        checkout,
        inspect_images,
        build_images,
        toolchain,
        antares_database,
        commands,
        antares_build,
        antares_browsers,
        cleanup,
        graphato,
        current_master,
        graphato_source,
        graphato_bootstrap,
        music_preflight,
        music_sync,
        paperless_preflight,
        paperless,
        gitea_preflight,
        gitea_bootstrap,
        hub_bootstrap_preflight,
        hub_bootstrap,
        hub_deploy_preflight,
        hub_image,
        hub_deploy,
        demo,
    ]
}


def main():
    c = json.loads(Path(sys.argv[1]).read_text())
    if c["values"].get("database_url"):
        os.environ["TEST_DATABASE_URL"] = c["values"]["database_url"]
    if c["step"]["action"] == "command":
        run(*c["step"]["command"])
        result = {}
    else:
        result = ACTIONS[c["step"]["action"]](c)
    Path(c["output"]).write_text(json.dumps(result))


if __name__ == "__main__":
    main()

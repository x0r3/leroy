"""Reviewed Python translations of the live Jenkins inventory (see docs/jenkins-inventory.json)."""

import json
from pathlib import Path

from .schema import Parameter as P
from .schema import Pipeline
from .schema import Step as S


def chain(*steps):
    for previous, step in zip(steps, steps[1:], strict=False):
        if not step.needs:
            step.needs = [previous.id]
    return list(steps)


def catalog(config=None):
    config = config or {}
    provenance_path = Path(__file__).with_name("inventory.json")
    provenance = json.loads(provenance_path.read_text())
    jobs = {j["name"]: j for j in provenance["jobs"]}
    repos = {
        "home": "http://gitea:3000/gitea-admin/home-lab-service-collection.git",
        "hub": "http://gitea:3000/gitea-admin/nikicas-hub.git",
        "graphato": "http://gitea:3000/gitea-admin/graphato.git",
        "antares": "https://github.com/x0r3/antares.git",
    }

    def params(job):
        result = []
        for d in jobs[job]["parameter_definitions"]:
            d = dict(d)
            if d["kind"] == "choice" and d["choices"]:
                d["default"] = d["choices"][0]
            if d["name"] == "RELEASE_COMMIT":
                d.update(required=True, pattern="[a-f0-9]{40}")
            result.append(P(**d))
        return result

    def checkout():
        return S(
            id="checkout", name="Checkout pinned revision", action="checkout", timeout=1200, secrets=["git"]
        )

    def make(id, group, repo, steps, **kwargs):
        source = jobs[id]
        # Jenkins stages without a separate timeout share the pipeline budget.
        # Do not introduce Step's thirty-minute default during translation.
        for step in steps:
            if "timeout" not in step.model_fields_set:
                step.timeout = kwargs.get("timeout", Pipeline.model_fields["timeout"].default)
        return Pipeline(
            id=id,
            name=id,
            description=kwargs.pop("description", ""),
            group=group,
            repository=repos.get(repo, repo),
            steps=steps,
            parameters=params(id),
            source={
                "repository": source["source_repository"],
                "commit": source["source_commit"],
                "jenkins_sha256": source["sha256"],
                "script_sha256": source["script_sha256"],
                "stages": source["stages"],
            },
            **kwargs,
        )

    pipelines = []
    for id, group, repo in [("home-lab-ci", "Home Lab", "home"), ("nikicas-hub-ci", "Nikicas Hub", "hub")]:
        pipelines.append(
            make(
                id,
                group,
                repo,
                chain(
                    checkout(),
                    S(id="inspect", name="Inspect changes and CI policy", action="inspect_images"),
                    S(
                        id="publish",
                        name="Build and publish images",
                        action="build_images",
                        condition="build_required",
                        timeout=14400,
                        secrets=["registry"],
                        artifacts=[".leroy-results/images.json"],
                    ),
                ),
                poll_seconds=120,
                timeout=18000,
                description="Commit-bound Docker images with explicit skip reasons",
            )
        )
    pipelines.append(
        make(
            "antares-ci",
            "Antares",
            "antares",
            chain(
                checkout(),
                S(id="toolchain", name="Toolchain", action="toolchain"),
                S(id="postgres", name="Isolated PostgreSQL", action="antares_database"),
                S(
                    id="dependencies",
                    name="Dependencies and security",
                    action="commands",
                    options={
                        "commands": [["npm", "ci"], ["npm", "audit", "--omit=dev", "--audit-level=high"]]
                    },
                ),
                S(
                    id="static",
                    name="Static validation",
                    action="commands",
                    options={"commands": [["npm", "run", "lint"], ["npm", "run", "typecheck"]]},
                ),
                S(
                    id="tests",
                    name="Unit and integration tests",
                    action="commands",
                    options={"commands": [["npm", "test"], ["npm", "run", "test:integration"]]},
                    artifacts=["coverage/**"],
                ),
                S(id="build", name="Production artifacts", action="antares_build"),
                S(
                    id="browsers",
                    name="Cross-browser end-to-end tests",
                    action="antares_browsers",
                    artifacts=["playwright-report/**", "test-results/**"],
                ),
                S(id="cleanup", name="Clean isolated resources", action="cleanup", always=True),
            ),
            concurrency="replace",
            poll_seconds=300,
            timeout=1800,
            description="Security, type, integration, image and browser gates",
        )
    )

    def graph_step(id, name, cmd, **kw):
        return S(id=id, name=name, action="graphato", options={"command": cmd}, **kw)

    pipelines.append(
        make(
            "graphato-ci",
            "Graphato",
            "graphato",
            chain(
                checkout(),
                graph_step(
                    "needed", "Check deployed revision", "release-needed", secrets=["graphato-deploy"]
                ),
                graph_step(
                    "boundaries", "Fast release boundaries", "basic-checks", condition="release_needed"
                ),
                graph_step(
                    "server",
                    "Build immutable server and worker",
                    "package",
                    condition="release_needed",
                    timeout=14400,
                    artifacts=[
                        ".leroy-results/release-transfer-timings.json",
                        ".leroy-results/release-manifest.json",
                    ],
                ),
                graph_step(
                    "desktop",
                    "Build Windows portable client",
                    "package-desktop",
                    condition="release_needed",
                    timeout=14400,
                    artifacts=[".leroy-results/desktop-release-manifest.json"],
                ),
                S(
                    id="current",
                    name="Check current master",
                    action="current_master",
                    secrets=["git"],
                    condition="release_needed",
                ),
                graph_step(
                    "deploy",
                    "Backup, migrate and deploy",
                    "deploy",
                    condition="is_current",
                    secrets=["graphato-deploy"],
                ),
                S(
                    id="acceptance",
                    name="Schedule release acceptance",
                    action="child",
                    condition="is_current",
                    options={
                        "pipeline": "graphato-release-acceptance",
                        "wait": False,
                        "parameter_sources": {"RELEASE_COMMIT": "commit"},
                    },
                ),
                graph_step("publish", "Publish Windows client", "publish-desktop", condition="is_current"),
                graph_step("cleanup", "Clean build resources", "cleanup", always=True),
            ),
            poll_seconds=120,
            timeout=14400,
            resource="graphato-delivery",
            description="Delivery and Windows publication; acceptance is tracked separately",
        )
    )
    for suite in ("web", "quality"):
        pipelines.append(
            make(
                "graphato-postdeploy-" + suite,
                "Graphato",
                "graphato",
                chain(
                    checkout(),
                    S(
                        id="verify",
                        name=f"Verify {suite} in isolated target environment",
                        action="graphato",
                        options={"command": "postdeploy", "suite": suite},
                        timeout=25200,
                        secrets=["graphato-deploy"],
                        artifacts=[f"target/postdeploy-{suite}/**"],
                    ),
                ),
                timeout=25200,
                description="Release-bound verification receipts, including partial groups",
            )
        )
    pipelines.append(
        make(
            "graphato-release-acceptance",
            "Graphato",
            "graphato",
            chain(
                checkout(),
                S(
                    id="web",
                    name="Browser acceptance",
                    action="child",
                    timeout=25200,
                    continue_on_error=True,
                    options={
                        "pipeline": "graphato-postdeploy-web",
                        "wait": True,
                        "parameter_sources": {"RELEASE_COMMIT": "commit"},
                        "parameters": {"CHECK_GROUP": "all"},
                    },
                ),
                S(
                    id="quality",
                    name="Quality acceptance",
                    action="child",
                    timeout=25200,
                    continue_on_error=True,
                    always=True,
                    options={
                        "pipeline": "graphato-postdeploy-quality",
                        "wait": True,
                        "parameter_sources": {"RELEASE_COMMIT": "commit"},
                        "parameters": {"CHECK_GROUP": "all"},
                    },
                ),
                graph_step(
                    "identity",
                    "Verify common release identity and total",
                    "release-status",
                    always=True,
                    secrets=["graphato-deploy"],
                    artifacts=["release-status.json"],
                ),
            ),
            timeout=28800,
            description="Full acceptance requires both complete suites and a matching release receipt",
        )
    )
    pipelines.append(
        make(
            "graphato-bootstrap-host",
            "Operations",
            "home",
            chain(
                checkout(),
                S(
                    id="source",
                    name="Checkout reviewed Graphato host policy",
                    action="graphato_source",
                    secrets=["git"],
                ),
                S(
                    id="transport",
                    name="Bootstrap transport checks",
                    command=[
                        "python3",
                        "-m",
                        "unittest",
                        "discover",
                        "-s",
                        "jenkins/graphato",
                        "-p",
                        "test_bootstrap.py",
                        "-v",
                    ],
                ),
                S(
                    id="bootstrap",
                    name="Inspect or initialize host",
                    action="graphato_bootstrap",
                    secrets=["graphato-bootstrap", "graphato-deploy"],
                ),
            ),
            timeout=3600,
            resource="graphato-host",
        )
    )
    pipelines.append(
        make(
            "music-library-sync-smartphone",
            "Operations",
            "home",
            chain(
                checkout(),
                S(
                    id="preflight",
                    name="Validate sources and SSH transport",
                    action="music_preflight",
                    secrets=["music-ssh"],
                ),
                S(id="sync", name="Synchronize music library", action="music_sync", secrets=["music-ssh"]),
            ),
            timeout=7200,
            schedule="H 3 * * *",
            resource="music-phone",
        )
    )
    paperless = make(
        "paperless-ngx-bootstrap-rules",
        "Operations",
        "home",
        chain(
            checkout(),
            S(id="preflight", name="Validate rules and API settings", action="paperless_preflight"),
            S(
                id="rules",
                name="Reconcile Paperless metadata and rules",
                action="paperless",
                secrets=["paperless"],
            ),
        ),
    )
    paperless.parameters = [
        P(name="PAPERLESS_API_URL", required=True),
        P(name="TIMEOUT_SECONDS", kind="integer", default=30),
        P(name="DRY_RUN", kind="boolean", default=False),
    ]
    pipelines.append(paperless)
    gitea = make(
        "gitea-bootstrap-repo",
        "Operations",
        "",
        chain(
            S(id="preflight", name="Validate Gitea settings", action="gitea_preflight"),
            S(
                id="bootstrap",
                name="Ensure administrator and repository",
                action="gitea_bootstrap",
                secrets=["gitea-admin"],
            ),
        ),
    )
    gitea.parameters = [
        P(name="GITEA_URL", required=True),
        P(name="GITEA_CONTAINER_NAME", required=True),
        P(name="ENSURE_GITEA_ADMIN_LOGIN", kind="boolean", default=True),
        P(name="GITEA_ADMIN_EMAIL", default="admin@leroy.test"),
        P(name="GITEA_OWNER", required=True),
        P(name="GITEA_REPO", required=True),
        P(name="GITEA_REPO_PRIVATE", kind="boolean", default=True),
        P(name="GITEA_DEFAULT_BRANCH", default="main"),
        P(name="GITEA_WAIT_SECONDS", kind="integer", default=60),
    ]
    pipelines.append(gitea)
    pipelines.append(
        make(
            "nikicas-hub-bootstrap-host",
            "Operations",
            "home",
            chain(
                checkout(),
                S(
                    id="preflight",
                    name="Validate host and deploy identity",
                    action="hub_bootstrap_preflight",
                    secrets=["hub-bootstrap", "hub-deploy"],
                ),
                S(
                    id="bootstrap",
                    name="Bootstrap host with Ansible",
                    action="hub_bootstrap",
                    secrets=["hub-bootstrap", "hub-deploy"],
                ),
            ),
            resource="hub-host",
            timeout=7200,
        )
    )
    pipelines.append(
        make(
            "nikicas-hub-deploy",
            "Nikicas Hub",
            "hub",
            chain(
                checkout(),
                S(id="preflight", name="Validate deployment settings", action="hub_deploy_preflight"),
                S(
                    id="image",
                    name="Pull and export selected image",
                    action="hub_image",
                    secrets=["registry"],
                ),
                S(
                    id="deploy",
                    name="Transfer and activate remote deployment",
                    action="hub_deploy",
                    secrets=["hub-deploy", "hub-app"],
                ),
            ),
            resource="hub-delivery",
            timeout=7200,
        )
    )
    for pipeline in pipelines:
        selectors = {
            "music-library-sync-smartphone": {"music-ssh": ["SSH_CREDENTIALS_ID"]},
            "nikicas-hub-bootstrap-host": {
                "hub-bootstrap": ["BOOTSTRAP_SSH_CREDENTIALS_ID"],
                "hub-deploy": ["DEPLOY_SSH_CREDENTIALS_ID"],
            },
            "nikicas-hub-deploy": {
                "git": ["GIT_CREDENTIALS_ID"],
                "hub-deploy": ["SSH_CREDENTIALS_ID"],
                "registry": ["REGISTRY_CREDENTIALS_ID"],
                "hub-app": [
                    "DEFAULT_ADMIN_LOGIN_SECRET_CREDENTIALS_ID",
                    "EVENT_HASH_SALT_CREDENTIALS_ID",
                    "APP_SALT_CREDENTIALS_ID",
                ],
            },
        }
        pipeline.credential_parameters = selectors.get(pipeline.id, {})
        overrides = config.get("pipelines", {}).get(pipeline.id, {})
        defaults = overrides.get("defaults", {})
        for param in pipeline.parameters:
            if param.name in defaults:
                param.default = param.validate_value(defaults[param.name])
            elif param.name == "GIT_URL" and "repository" in overrides:
                param.default = overrides["repository"]
        for key in ("repository", "ref", "profile", "enabled", "resource", "poll_seconds", "schedule"):
            if key in overrides:
                setattr(pipeline, key, overrides[key])
        yield Pipeline.model_validate(pipeline.model_dump())
    if config.get("demo", False):
        yield Pipeline(
            id="leroy-demo",
            name="Leroy · Execution laboratory",
            group="Leroy",
            description="Real commands for exercising graph, logs, artifacts and failures",
            concurrency="parallel",
            parameters=[
                P(name="FAIL", kind="boolean", default=False),
                P(name="SECONDS", kind="integer", default=2),
            ],
            steps=[
                S(id="prepare", name="Prepare workspace", action="demo", options={"phase": "prepare"}),
                S(id="unit", name="Unit checks", action="demo", needs=["prepare"], options={"phase": "unit"}),
                S(
                    id="lint",
                    name="Static checks",
                    action="demo",
                    needs=["prepare"],
                    options={"phase": "lint"},
                ),
                S(
                    id="package",
                    name="Package results",
                    action="demo",
                    needs=["unit", "lint"],
                    options={"phase": "package"},
                    artifacts=["result.json"],
                ),
                S(
                    id="cleanup",
                    name="Clean workspace",
                    action="demo",
                    needs=["package"],
                    always=True,
                    options={"phase": "cleanup"},
                ),
            ],
        )

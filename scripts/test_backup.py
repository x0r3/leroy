"""Quiesce the isolated stack and restore its DB and file volume into private targets."""

import json
import subprocess
import uuid
from contextlib import closing
from pathlib import Path

from sqlalchemy import create_engine, text
from test_support import api

COMPOSE = ["docker", "compose", "-p", "leroy-test", "-f", "compose.yaml", "-f", "compose.test.yaml"]
PG = ["docker", "exec", "leroy-test-postgres-1"]
directory = Path("test-results/offline-backup")
directory.mkdir(parents=True, exist_ok=True)
name = "leroy_restore_" + uuid.uuid4().hex
password = Path(".local/db_password").read_text().strip()
engine = create_engine(f"postgresql+psycopg://leroy:{password}@127.0.0.1:55439/{name}")


def run(*args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, **kwargs)


with closing(api()) as client:
    for state in ("queued", "running", "waiting"):
        assert not client.get("/api/runs", params={"status": state, "limit": 1}).json(), "Drain jobs first"
    assert not any(p["enabled"] for p in client.get("/api/pipelines").json()), (
        "Pause automatic triggers first"
    )

try:
    run(*COMPOSE, "stop", "runner", "controller")
    with (directory / "database.dump").open("wb") as output:
        subprocess.run([*PG, "pg_dump", "-U", "leroy", "-Fc", "leroy"], stdout=output, check=True)
    with (directory / "data.tar.gz").open("wb") as output:
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--volumes-from",
                "leroy-test-controller-1:ro",
                "--entrypoint",
                "tar",
                "leroy-controller:local",
                "-C",
                "/data",
                "-czf",
                "-",
                ".",
            ],
            stdout=output,
            check=True,
        )
finally:
    run(*COMPOSE, "start", "controller", "runner")

run(*PG, "createdb", "-U", "leroy", name)
run("docker", "volume", "create", name)
try:
    with (directory / "database.dump").open("rb") as source:
        run(
            "docker",
            "exec",
            "-i",
            "leroy-test-postgres-1",
            "pg_restore",
            "-U",
            "leroy",
            "--exit-on-error",
            "-d",
            name,
            stdin=source,
        )
    with (directory / "data.tar.gz").open("rb") as source:
        run(
            "docker",
            "run",
            "--rm",
            "-i",
            "--user",
            "0",
            "--mount",
            f"type=volume,source={name},target=/data",
            "--entrypoint",
            "tar",
            "leroy-controller:local",
            "-C",
            "/data",
            "-xzf",
            "-",
            stdin=source,
        )
    with engine.connect() as db:
        artifacts = [dict(r) for r in db.execute(text("SELECT id, size, sha256 FROM artifacts")).mappings()]
        logs = [
            dict(r)
            for r in db.execute(
                text("SELECT run_id, id, log_bytes FROM steps WHERE log_bytes > 0")
            ).mappings()
        ]
        assert db.scalar(text("SELECT count(*) FROM runs WHERE status IN ('running','waiting')")) == 0
    verifier = """
import hashlib,json,pathlib,sys
manifest=json.load(sys.stdin)
for item in manifest['artifacts']:
 data=(pathlib.Path('/data/artifacts')/item['id']).read_bytes()
 assert len(data)==item['size'] and hashlib.sha256(data).hexdigest()==item['sha256']
for item in manifest['logs']:
 data=(pathlib.Path('/data/logs')/item['run_id']/(item['id']+'.log')).read_bytes()
 assert len(data)>=item['log_bytes']
print(json.dumps({'artifacts_verified':len(manifest['artifacts']),'logs_verified':len(manifest['logs']),'status':'passed'}))
"""
    result = (
        run(
            "docker",
            "run",
            "--rm",
            "-i",
            "--user",
            "0",
            "--mount",
            f"type=volume,source={name},target=/data,readonly",
            "--entrypoint",
            "python",
            "leroy-controller:local",
            "-c",
            verifier,
            input=json.dumps({"artifacts": artifacts, "logs": logs}).encode(),
        )
        .stdout.decode()
        .strip()
    )
    (directory / "result.json").write_text(result + "\n", encoding="utf-8")
    print(result)
finally:
    engine.dispose()
    run(*PG, "dropdb", "-U", "leroy", name)
    run("docker", "volume", "rm", name)

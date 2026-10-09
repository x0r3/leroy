"""Runs only on the NAS, against explicitly owned Leroy test resources."""

import hashlib
import hmac
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import tarfile
import time
import uuid

os.umask(0o077)
ROOT = pathlib.Path("/volume1/docker/leroy-nas-parity")
assert (ROOT / ".leroy-owned").is_file()
FOLDER = ROOT / "backups" / ("acceptance-" + uuid.uuid4().hex)
FOLDER.mkdir(parents=True)
PG = "leroy-nas-parity-postgres-1"
CONTROLLER = "leroy-nas-parity-controller-1"
RUNNER = "leroy-nas-parity-runner-1"


def command(*args, **kwargs):
    return subprocess.run(list(args), check=True, capture_output=True, timeout=300, **kwargs).stdout


def inspect(name):
    value = json.loads(command("docker", "inspect", name))[0]
    assert value["Config"]["Labels"]["com.docker.compose.project"] == "leroy-nas-parity"
    return value


def query(database, sql):
    return command("docker", "exec", PG, "psql", "-U", "leroy", "-d", database, "-At", "-c", sql)


def fingerprint(database):
    tables = (
        query(database, "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
        .decode()
        .split()
    )
    result = {}
    for table in tables:
        assert re.fullmatch("[a-z_0-9]+", table)
        rows = query(database, 'COPY (SELECT to_jsonb(t)::text FROM "' + table + '" t ORDER BY 1) TO STDOUT')
        result[table] = {"sha256": hashlib.sha256(rows).hexdigest(), "rows": len(rows.splitlines())}
    return result


controller = inspect(CONTROLLER)
inspect(RUNNER)
inspect(PG)
assert (
    query("leroy", "SELECT count(*) FROM runs WHERE status IN ('queued','running','waiting')").strip() == b"0"
)
assert query("leroy", "SELECT count(*) FROM pipelines WHERE enabled").strip() == b"0"
image = controller["Image"]
(network,) = controller["NetworkSettings"]["Networks"]
key = ROOT / "backup-test-key"
password = key.read_bytes()
assert len(password) >= 40
try:
    command("docker", "stop", RUNNER, CONTROLLER)
    try:
        expected = fingerprint("leroy")
        with (FOLDER / "database.dump").open("wb") as output:
            subprocess.run(
                ["docker", "exec", PG, "pg_dump", "-U", "leroy", "-Fc", "leroy"],
                stdout=output,
                stderr=subprocess.PIPE,
                check=True,
                timeout=180,
            )
        with (FOLDER / "data.tar.gz").open("wb") as output:
            subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--network",
                    "none",
                    "--memory",
                    "256m",
                    "--cpus",
                    ".5",
                    "--volumes-from",
                    CONTROLLER + ":ro",
                    "--entrypoint",
                    "tar",
                    image,
                    "-C",
                    "/data",
                    "-czf",
                    "-",
                    ".",
                ],
                stdout=output,
                stderr=subprocess.PIPE,
                check=True,
                timeout=600,
            )
        config_files = ["config", "compose.yaml", "dind.sh"]
        if (ROOT / "compose.release.json").is_file():
            config_files.append("compose.release.json")
        config = command("tar", "-C", str(ROOT), "-czf", "-", *config_files)
        encrypted = command(
            "openssl",
            "enc",
            "-aes-256-cbc",
            "-pbkdf2",
            "-iter",
            "200000",
            "-salt",
            "-pass",
            "file:" + str(key),
            input=config,
        )
        (FOLDER / "configuration.enc").write_bytes(encrypted)
        tag = hmac.new(password, encrypted, hashlib.sha256).hexdigest()
        assert hmac.compare_digest(
            tag, hmac.new(password, (FOLDER / "configuration.enc").read_bytes(), hashlib.sha256).hexdigest()
        )
        recovered = command(
            "openssl",
            "enc",
            "-d",
            "-aes-256-cbc",
            "-pbkdf2",
            "-iter",
            "200000",
            "-pass",
            "file:" + str(key),
            input=encrypted,
        )
        assert recovered == config
    finally:
        command("docker", "start", CONTROLLER, RUNNER)
    database = "leroy_restore_" + uuid.uuid4().hex
    volume = "leroy-nas-parity-restore-" + uuid.uuid4().hex
    restore_controller = volume + "-controller"
    label = "io.leroy.backup-test=" + volume
    manifest = {
        "at": time.time(),
        "folder": str(FOLDER),
        "source_database": "leroy",
        "restored_database": database,
        "restore_volume": volume,
        "controller_image": image,
        "tables": expected,
        "configuration_hmac_sha256": tag,
        "files": {
            p.name: {
                "bytes": p.stat().st_size,
                "sha256": hashlib.file_digest(p.open("rb"), "sha256").hexdigest(),
            }
            for p in FOLDER.iterdir()
            if p.is_file()
        },
    }
    (FOLDER / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    command("docker", "exec", PG, "createdb", "-U", "leroy", database)
    command("docker", "volume", "create", "--label", label, volume)
    restored_config = FOLDER / "restore-config"
    restored_config.mkdir()
    try:
        with (FOLDER / "database.dump").open("rb") as source:
            command(
                "docker",
                "exec",
                "-i",
                PG,
                "pg_restore",
                "-U",
                "leroy",
                "--exit-on-error",
                "-d",
                database,
                stdin=source,
            )
        with (FOLDER / "data.tar.gz").open("rb") as source:
            command(
                "docker",
                "run",
                "--rm",
                "-i",
                "--network",
                "none",
                "--user",
                "0",
                "--memory",
                "256m",
                "--cpus",
                ".5",
                "--mount",
                "type=volume,source=" + volume + ",target=/data",
                "--entrypoint",
                "tar",
                image,
                "-C",
                "/data",
                "-xzf",
                "-",
                stdin=source,
            )
        assert fingerprint(database) == expected
        artifacts = json.loads(
            query(database, "SELECT coalesce(json_agg(t),'[]') FROM (SELECT id,size,sha256 FROM artifacts) t")
        )
        logs = json.loads(
            query(
                database,
                "SELECT coalesce(json_agg(t),'[]') FROM (SELECT run_id,id,log_bytes FROM steps WHERE log_bytes>0) t",
            )
        )
        verifier = """import hashlib,json,pathlib,sys
manifest=json.load(sys.stdin)
for item in manifest['artifacts']:
 path=pathlib.Path('/data/artifacts')/item['id']
 assert path.stat().st_size==item['size']
 with path.open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==item['sha256']
for item in manifest['logs']:
 path=pathlib.Path('/data/logs')/item['run_id']/(item['id']+'.log')
 assert path.stat().st_size>=item['log_bytes']
print(json.dumps({'artifacts_verified':len(manifest['artifacts']),'logs_verified':len(manifest['logs'])}))
"""
        verified = json.loads(
            command(
                "docker",
                "run",
                "--rm",
                "-i",
                "--network",
                "none",
                "--user",
                "0",
                "--memory",
                "256m",
                "--cpus",
                ".5",
                "--mount",
                "type=volume,source=" + volume + ",target=/data,readonly",
                "--entrypoint",
                "python",
                image,
                "-c",
                verifier,
                input=json.dumps({"artifacts": artifacts, "logs": logs}).encode(),
            )
        )
        with tarfile.open(fileobj=io.BytesIO(recovered), mode="r:gz") as archive:
            for item in archive.getmembers():
                name = pathlib.PurePosixPath(item.name)
                assert not name.is_absolute() and ".." not in name.parts
                if item.isdir():
                    continue
                assert item.isfile()
                path = restored_config.joinpath(*name.parts)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(archive.extractfile(item).read())
                path.chmod(item.mode & 0o777)
        env = restored_config / "config/controller.env"
        lines = env.read_text().splitlines()
        for i, line in enumerate(lines):
            if line.startswith("LEROY_DATABASE_URL="):
                assert line.endswith("@postgres/leroy")
                lines[i] = line.removesuffix("/leroy") + "/" + database
        env.write_text("\n".join(lines) + "\n")
        # Recovered credentials and definition configuration are supplied to the
        # temporary controller. No port, runner or external trigger is enabled.
        command(
            "docker",
            "run",
            "-d",
            "--name",
            restore_controller,
            "--label",
            label,
            "--network",
            network,
            "--memory",
            "256m",
            "--cpus",
            ".5",
            "--env-file",
            str(env),
            "-e",
            "LEROY_ADMIN_PASSWORD_FILE=/run/secrets/admin_password",
            "-e",
            "LEROY_RUNNER_TOKEN_FILE=/run/secrets/runner_token",
            "-v",
            volume + ":/data",
            "-v",
            str(restored_config / "config/leroy.toml") + ":/config/leroy.toml:ro",
            "-v",
            str(restored_config / "config/admin_password") + ":/run/secrets/admin_password:ro",
            "-v",
            str(restored_config / "config/runner_token") + ":/run/secrets/runner_token:ro",
            image,
        )
        health = 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8088/health/ready",timeout=5).status)'
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            try:
                assert command("docker", "exec", restore_controller, "python", "-c", health).strip() == b"200"
                break
            except subprocess.CalledProcessError:
                time.sleep(2)
        else:
            raise TimeoutError("Restored controller did not become ready")
        manifest.update(
            verified,
            passed=True,
            restored_controller_ready=True,
            same_database_rows_and_hashes=True,
            configuration_decrypted_and_reused=True,
            production_access=False,
        )
        (FOLDER / "result.json").write_text(json.dumps(manifest, indent=2) + "\n")
        print(json.dumps(manifest), flush=True)
    finally:
        subprocess.run(["docker", "rm", "-f", restore_controller], capture_output=True, timeout=90)
        command("docker", "exec", PG, "dropdb", "-U", "leroy", database)
        info = json.loads(command("docker", "volume", "inspect", volume))[0]
        assert info["Labels"]["io.leroy.backup-test"] == volume
        command("docker", "volume", "rm", volume)
        assert restored_config.resolve().is_relative_to(FOLDER.resolve())
        shutil.rmtree(restored_config)
finally:
    key.unlink(missing_ok=True)

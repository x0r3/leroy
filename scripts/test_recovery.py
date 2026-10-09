"""Validate fresh migrations and binary pg_dump/pg_restore in private test databases.

Only connects to leroy-test-postgres-1 and port 55439. Never changes the source DB.
This tests database recovery; a coherent deployment backup must also include /data.
"""

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

from sqlalchemy import create_engine, text

PREFIX = ["docker", "exec", "leroy-test-postgres-1"]
name = "leroy_recovery_" + uuid.uuid4().hex
password = Path(".local/db_password").read_text().strip()
url = f"postgresql+psycopg://leroy:{password}@127.0.0.1:55439/{name}"
result = {}


def command(*args, **kwargs):
    return subprocess.run([*PREFIX, *args], check=True, capture_output=True, **kwargs)


command("createdb", "-U", "leroy", name)
engine = create_engine(url)
try:
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env={**os.environ, "LEROY_DATABASE_URL": url},
        check=True,
        capture_output=True,
    )
    with engine.connect() as db:
        assert db.scalar(text("SELECT version_num FROM alembic_version")) == "0003"
        result["fresh_migration"] = "passed"
    engine.dispose()
    command("dropdb", "-U", "leroy", name)
    command("createdb", "-U", "leroy", name)
    directory = Path("test-results/recovery")
    directory.mkdir(parents=True, exist_ok=True)
    dump = directory / "database.dump"
    with dump.open("wb") as output:
        subprocess.run([*PREFIX, "pg_dump", "-U", "leroy", "-Fc", "leroy"], stdout=output, check=True)
    with dump.open("rb") as source:
        subprocess.run(
            [
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
            ],
            stdin=source,
            check=True,
            capture_output=True,
        )
    with engine.connect() as db:
        assert db.scalar(text("SELECT version_num FROM alembic_version")) == "0003"
        result["restored_runs"] = db.scalar(text("SELECT count(*) FROM runs"))
        result["restored_events"] = db.scalar(text("SELECT count(*) FROM events"))
        result["restored_artifacts"] = db.scalar(text("SELECT count(*) FROM artifacts"))
        assert result["restored_runs"] > 0 and result["restored_events"] > 0
        result["pg_restore"] = "passed"
    (directory / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))
finally:
    engine.dispose()
    command("dropdb", "-U", "leroy", name)

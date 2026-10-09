"""Real PostgreSQL concurrency and crash-boundary tests, each in a private schema."""

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from leroy.api import create_app
from leroy.config import Settings
from leroy.db import Base, PipelineRow, Run, now
from leroy.engine import claim, enqueue, reconcile, request_cancel
from leroy.schema import Pipeline, Step


@pytest.fixture
def database():
    url = os.getenv("LEROY_TEST_DATABASE_URL")
    if not url:
        pytest.skip("LEROY_TEST_DATABASE_URL must point to isolated PostgreSQL")
    admin = create_engine(url)
    schema = "test_" + uuid.uuid4().hex
    with admin.begin() as db:
        db.execute(text(f'CREATE SCHEMA "{schema}"'))
    url = url + ("&" if "?" in url else "?") + "options=-csearch_path%3D" + schema
    engine = create_engine(url)
    with engine.begin() as db:
        db.execute(text("CREATE SEQUENCE run_number_seq"))
        Base.metadata.create_all(db)
    yield make_url(url), sessionmaker(engine, expire_on_commit=False)
    engine.dispose()
    with admin.begin() as db:
        db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    admin.dispose()


def install(sessions, id="test", **kwargs):
    spec = Pipeline(id=id, name=id, steps=[Step(id="work", name="work", command=["true"])], **kwargs)
    with sessions.begin() as db:
        row = PipelineRow(id=id, spec=spec.model_dump())
        db.add(row)
        db.flush()
        return enqueue(db, row, {}).id


def test_concurrent_claims_enforce_capacity_without_duplicate_assignment(database):
    _, sessions = database
    install(sessions, concurrency="parallel")
    with sessions.begin() as db:
        for _ in range(29):
            enqueue(db, db.get(PipelineRow, "test"), {})

    def acquire(_):
        with sessions.begin() as db:
            return claim(db, "one-runner", ["default"], 7)

    with ThreadPoolExecutor(max_workers=12) as pool:
        claimed = [r for r in pool.map(acquire, range(30)) if r]
    assert len(claimed) == 7
    assert len({r["id"] for r in claimed}) == 7
    with sessions() as db:
        assert len(list(db.scalars(select(Run).where(Run.status == "queued")))) == 23


def test_resource_lock_and_expired_attempt_do_not_retry_side_effects(database):
    _, sessions = database
    first = install(sessions, "one", resource="target")
    second = install(sessions, "two", resource="target")
    with sessions.begin() as db:
        assert claim(db, "runner", ["default"], 5)["id"] == first
        assert claim(db, "runner", ["default"], 5) is None
        db.get(Run, first).lease_until = now() - timedelta(seconds=1)
    with sessions.begin() as db:
        reconcile(db)
        old = db.get(Run, first)
        assert old.status == "interrupted" and old.token_hash is None
        assert claim(db, "runner", ["default"], 5)["id"] == second


def test_cancel_parent_cascades_and_enqueue_deduplicates(database):
    _, sessions = database
    parent = install(sessions)
    with sessions.begin() as db:
        row = db.get(PipelineRow, "test")
        child = enqueue(db, row, {}, parent_id=parent, dedupe_key="child")
        assert enqueue(db, row, {}, parent_id=parent, dedupe_key="child").id == child.id
        request_cancel(db, db.get(Run, parent), "test")
    with sessions() as db:
        assert all(r.status == "cancelled" for r in db.scalars(select(Run)))


@pytest.mark.parametrize(
    "chain,resources,waits,target,status,detail",
    [
        (["a"], {"a": None}, [True], "a", 422, "cycle"),
        (["a", "b"], {"a": None, "b": None}, [False, False], "a", 422, "cycle"),
        (["a"], {"a": "host", "b": "host"}, [True], "b", 422, "waiting ancestor a"),
        (["a", "b"], {"a": "host", "b": None, "c": "host"}, [True, True], "c", 422, "waiting ancestor a"),
        (["a", "b"], {"a": "host", "b": None, "c": "host"}, [False, True], "c", 200, ""),
        (["a"], {"a": "host", "b": "host"}, [False], "b", 200, ""),
        (["a"], {"a": "host", "b": "other"}, [True], "b", 200, ""),
    ],
)
def test_child_calls_reject_cycles_and_impossible_resource_waits(
    database, tmp_path, chain, resources, waits, target, status, detail
):
    from leroy.engine import digest

    url, sessions = database
    with sessions.begin() as db:
        for identifier, resource in resources.items():
            if identifier in chain:
                position = chain.index(identifier)
                next_pipeline = chain[position + 1] if position + 1 < len(chain) else target
                step = Step(
                    id="child",
                    name="Child",
                    action="child",
                    options={"pipeline": next_pipeline, "wait": waits[position]},
                )
            else:
                step = Step(id="work", name="Work", command=["true"])
            spec = Pipeline(id=identifier, name=identifier, resource=resource, steps=[step])
            db.add(PipelineRow(id=identifier, spec=spec.model_dump()))
        db.flush()
        parent = None
        for identifier in chain:
            run = enqueue(
                db,
                db.get(PipelineRow, identifier),
                {},
                parent_id=parent.id if parent else None,
                dedupe_key=f"child:{parent.id}:child" if parent else None,
            )
            run.status, run.token_hash = "running", digest("test-attempt")
            run.lease_until = now() + timedelta(seconds=90)
            parent = run
        parent_id = parent.id
    settings = Settings(url, tmp_path, {}, "r" * 40, "admin-password-for-tests", "http://testserver", False)
    with TestClient(create_app(settings)) as client:
        endpoint = f"/internal/runs/{parent_id}/children/{target}"
        headers = {"Authorization": "Bearer test-attempt"}
        response = client.post(endpoint, headers=headers, json={"step_id": "child"})
        assert response.status_code == status, response.text
        if status == 422:
            assert detail in response.json()["detail"]
            with sessions() as db:
                assert not list(db.scalars(select(Run).where(Run.parent_id == parent_id)))
        else:
            child_id = response.json()["id"]
            assert client.post(endpoint, headers=headers, json={"step_id": "child"}).json()["id"] == child_id


def test_api_auth_fencing_idempotent_logs_and_no_false_success(database, tmp_path):
    url, sessions = database
    run_id = install(sessions)
    settings = Settings(url, tmp_path, {}, "r" * 40, "admin-password-for-tests", "http://testserver", False)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/runs").status_code == 401
        assert (
            client.post(
                "/api/auth/login", json={"username": "admin", "password": settings.admin_password}
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/auth/login",
                headers={"X-Leroy-Request": "1"},
                json={"username": "admin", "password": settings.admin_password},
            ).status_code
            == 200
        )
        assignment = client.post(
            "/internal/claim",
            headers={"Authorization": "Bearer " + settings.runner_token},
            json={"runner": "test", "profiles": ["default"], "capacity": 1},
        ).json()
        headers = {"Authorization": "Bearer " + assignment["token"]}
        base = "/internal/runs/" + run_id
        assert (
            client.post(base + "/complete", headers=headers, json={"status": "succeeded"}).status_code == 409
        )
        assert client.post(base + "/identity", headers=headers, json={"commit": "a" * 40}).status_code == 200
        assert client.post(base + "/identity", headers=headers, json={"commit": "b" * 40}).status_code == 409
        for _ in range(2):
            assert (
                client.post(base + "/logs/work?offset=0", headers=headers, content=b"first\n").json()[
                    "offset"
                ]
                == 6
            )
        assert client.get(f"/api/runs/{run_id}/logs/work").json()["text"] == "first\n"
        # A file write committed without its DB offset is truncated on retransmission.
        path = tmp_path / "logs" / run_id / "work.log"
        with path.open("ab") as handle:
            handle.write(b"uncommitted")
        client.post(base + "/logs/work?offset=6", headers=headers, content=b"second\n")
        assert path.read_bytes() == b"first\nsecond\n"
        artifact = client.post(base + "/artifacts/work?name=report.txt", headers=headers, content=b"report")
        artifact.raise_for_status()
        assert client.get("/api/artifacts/" + artifact.json()["id"]).content == b"report"
        from leroy.db import FileDeletion

        with sessions() as db:
            assert not list(db.scalars(select(FileDeletion)))
        client.post(base + "/steps/work", headers=headers, json={"status": "succeeded"})
        assert (
            client.post(base + "/complete", headers=headers, json={"status": "succeeded"}).status_code == 200
        )
        assert client.post(base + "/heartbeat", headers=headers).status_code == 409


@pytest.mark.parametrize(
    "cause,status",
    [("Parent step timeout exceeded", "timed_out"), ("Cancelled by operator", "cancelled")],
)
def test_completion_preserves_cancellation_cause_before_next_heartbeat(database, tmp_path, cause, status):
    from leroy.db import Event

    url, sessions = database
    run_id = install(sessions)
    settings = Settings(url, tmp_path, {}, "r" * 40, "admin-password-for-tests", "http://testserver", False)
    with TestClient(create_app(settings)) as client:
        with sessions.begin() as db:
            assignment = claim(db, "test", ["default"], 1)
            request_cancel(db, db.get(Run, run_id), cause)
        response = client.post(
            f"/internal/runs/{run_id}/complete",
            headers={"Authorization": "Bearer " + assignment["token"]},
            json={"status": "failed", "reason": "verify: Process exited with code 1"},
        )
        assert response.status_code == 200
        with sessions() as db:
            run = db.get(Run, run_id)
            assert (run.status, run.reason) == (status, cause)
            terminal = db.scalar(select(Event).where(Event.run_id == run_id, Event.kind == "run." + status))
            assert terminal.data["reason"] == cause


def test_busy_login_does_not_wait_for_the_password_check_lock(database, tmp_path):
    url, sessions = database
    settings = Settings(url, tmp_path, {}, "r" * 40, "admin-password-for-tests", "http://testserver", False)
    with TestClient(create_app(settings)) as client, ThreadPoolExecutor(max_workers=1) as pool:
        with sessions.begin() as db:
            db.execute(text("SELECT pg_advisory_xact_lock(7046102)"))
            future = pool.submit(
                client.post,
                "/api/auth/login",
                headers={"X-Leroy-Request": "1"},
                json={"username": "admin", "password": settings.admin_password},
            )
            response = future.result(timeout=2)
            assert response.status_code == 429 and response.headers["Retry-After"] == "1"
            assert client.get("/health/ready").status_code == 200
        response = client.post(
            "/api/auth/login",
            headers={"X-Leroy-Request": "1"},
            json={"username": "admin", "password": settings.admin_password},
        )
        assert response.status_code == 200


@pytest.mark.parametrize("phase", ["registration", "publication"])
def test_blocked_artifact_database_work_does_not_block_other_run_heartbeat(
    database, tmp_path, monkeypatch, phase
):
    import threading
    import time
    from concurrent.futures import TimeoutError as FutureTimeout
    from pathlib import Path

    url, sessions = database
    upload_id = install(sessions, "upload")
    heartbeat_id = install(sessions, "heartbeat")
    with sessions.begin() as db:
        assignments = [claim(db, "test", ["default"], 2), claim(db, "test", ["default"], 2)]
    tokens = {row["id"]: {"Authorization": "Bearer " + row["token"]} for row in assignments}
    settings = Settings(url, tmp_path, {}, "r" * 40, "admin-password-for-tests", "http://testserver", False)
    responsive = False
    writing, release_write = threading.Event(), threading.Event()
    original_open = Path.open

    class PausedFile:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self.handle.__exit__(*args)

        def write(self, data):
            writing.set()
            assert release_write.wait(5)
            return self.handle.write(data)

        def __getattr__(self, name):
            return getattr(self.handle, name)

    def open_file(path, mode="r", *args, **kwargs):
        handle = original_open(path, mode, *args, **kwargs)
        if phase == "publication" and path.parent == tmp_path / "artifacts" and mode == "xb":
            return PausedFile(handle)
        return handle

    monkeypatch.setattr(Path, "open", open_file)
    with TestClient(create_app(settings)) as client, ThreadPoolExecutor(max_workers=2) as pool:
        with sessions.begin() as blocker:
            blocker_pid = blocker.scalar(text("SELECT pg_backend_pid()"))
            if phase == "registration":
                blocker.scalar(select(Run).where(Run.id == upload_id).with_for_update())
            upload = pool.submit(
                client.post, f"/internal/runs/{upload_id}/artifacts/work?name=report.txt",
                headers=tokens[upload_id], content=b"report",
            )
            if phase == "publication":
                try:
                    assert writing.wait(3), "Registration must finish before locking publication"
                    blocker.scalar(select(Run).where(Run.id == upload_id).with_for_update())
                finally:
                    release_write.set()
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                with sessions() as observer:
                    blocked = observer.scalar(text(
                        "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                        "WHERE :blocker = ANY(pg_blocking_pids(pid)))"
                    ), {"blocker": blocker_pid})
                if blocked:
                    break
                time.sleep(0.01)
            assert blocked, "The upload must actually wait on the PostgreSQL row lock"
            heartbeat = pool.submit(
                client.post, f"/internal/runs/{heartbeat_id}/heartbeat", headers=tokens[heartbeat_id],
            )
            try:
                response = heartbeat.result(timeout=1)
                responsive = response.status_code == 200 and response.json()["cancel"] is False
            except FutureTimeout:
                pass
        upload.result(timeout=3).raise_for_status()
        heartbeat.result(timeout=3).raise_for_status()
    assert responsive, "An unrelated upload's database lock blocked the controller event loop"


def test_cancelled_upload_request_preserves_an_artifact_being_committed(database, tmp_path):
    import asyncio
    import hashlib
    import threading

    import httpx
    from sqlalchemy import event

    from leroy.db import Artifact, FileDeletion

    url, sessions = database
    run_id = install(sessions)
    with sessions.begin() as db:
        assignment = claim(db, "test", ["default"], 1)
    settings = Settings(url, tmp_path, {}, "r" * 40, "admin-password-for-tests", "http://testserver", False)
    app = create_app(settings)
    engine = app.state.sessions.kw["bind"]
    publishing, release = threading.Event(), threading.Event()
    content = b"An artifact must survive its request being cancelled during commit."

    def pause_publication(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().startswith("INSERT INTO artifacts "):
            publishing.set()
            assert release.wait(5), "Publication was not released"

    event.listen(engine, "before_cursor_execute", pause_publication)

    async def exercise():
        async with app.router.lifespan_context(app), httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://testserver"
        ) as client:
            request = asyncio.create_task(client.post(
                f"/internal/runs/{run_id}/artifacts/work?name=report.txt",
                headers={"Authorization": "Bearer " + assignment["token"]}, content=content,
            ))
            try:
                assert await asyncio.to_thread(publishing.wait, 3), "Publication did not reach PostgreSQL"
                request.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(request, 1)
                assert len(list((tmp_path / "artifacts").iterdir())) == 1
            finally:
                release.set()
            # Cancellation stops the HTTP task; publication still owns its commit and file.
            for _ in range(100):
                with sessions() as db:
                    artifact = db.scalar(select(Artifact).where(Artifact.run_id == run_id))
                if artifact is not None:
                    break
                await asyncio.sleep(0.02)
            assert artifact is not None
            assert artifact.sha256 == hashlib.sha256(content).hexdigest()
            assert artifact.size == len(content)
            assert (tmp_path / "artifacts" / artifact.id).read_bytes() == content
            with sessions() as db:
                assert db.get(FileDeletion, ("artifacts", artifact.id)) is None

    try:
        asyncio.run(exercise())
    finally:
        release.set()
        event.remove(engine, "before_cursor_execute", pause_publication)


def pause_log_flush(monkeypatch, log_path):
    import threading
    from pathlib import Path

    writing, release = threading.Event(), threading.Event()
    original_open = Path.open

    class PausedFile:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self.handle.__exit__(*args)

        def flush(self):
            writing.set()
            assert release.wait(10), "The test must release the simulated slow disk"
            return self.handle.flush()

        def __getattr__(self, name):
            return getattr(self.handle, name)

    def open_file(path, mode="r", *args, **kwargs):
        handle = original_open(path, mode, *args, **kwargs)
        return PausedFile(handle) if path == log_path and mode in ("w+b", "r+b") else handle

    monkeypatch.setattr(Path, "open", open_file)
    return writing, release


def test_blocked_log_flush_does_not_block_its_own_heartbeat(database, tmp_path, monkeypatch):
    from concurrent.futures import TimeoutError as FutureTimeout

    url, sessions = database
    run_id = install(sessions)
    with sessions.begin() as db:
        assignment = claim(db, "test", ["default"], 1)
    headers = {"Authorization": "Bearer " + assignment["token"]}
    settings = Settings(url, tmp_path, {}, "r" * 40, "admin-password-for-tests", "http://testserver", False)
    path = tmp_path / "logs" / run_id / "work.log"
    writing, release = pause_log_flush(monkeypatch, path)
    responsive = False
    with TestClient(create_app(settings)) as client, ThreadPoolExecutor(max_workers=2) as pool:
        upload = pool.submit(client.post, f"/internal/runs/{run_id}/logs/work", headers=headers, content=b"first\n")
        try:
            assert writing.wait(3)
            heartbeat = pool.submit(client.post, f"/internal/runs/{run_id}/heartbeat", headers=headers)
            try:
                response = heartbeat.result(timeout=1)
                responsive = response.status_code == 200 and response.json()["cancel"] is False
            except FutureTimeout:
                pass
        finally:
            release.set()
        upload.result(timeout=3).raise_for_status()
        heartbeat.result(timeout=3).raise_for_status()
    assert responsive, "A slow log flush held the run lock needed by its own heartbeat"
    assert path.read_bytes() == b"first\n"


def test_duplicate_log_upload_waits_for_durable_offset(database, tmp_path, monkeypatch):
    from concurrent.futures import TimeoutError as FutureTimeout

    url, sessions = database
    run_id = install(sessions)
    with sessions.begin() as db:
        assignment = claim(db, "test", ["default"], 1)
    headers = {"Authorization": "Bearer " + assignment["token"]}
    settings = Settings(url, tmp_path, {}, "r" * 40, "admin-password-for-tests", "http://testserver", False)
    path = tmp_path / "logs" / run_id / "work.log"
    writing, release = pause_log_flush(monkeypatch, path)
    endpoint = f"/internal/runs/{run_id}/logs/work"
    with TestClient(create_app(settings)) as client, ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(client.post, endpoint, headers=headers, content=b"first\n")
        try:
            assert writing.wait(3)
            retry = pool.submit(client.post, endpoint, headers=headers, content=b"must not overwrite")
            with pytest.raises(FutureTimeout):
                retry.result(timeout=0.2)
        finally:
            release.set()
        assert first.result(timeout=3).json() == retry.result(timeout=3).json() == {"offset": 6}
    assert path.read_bytes() == b"first\n"


def test_retention_defers_log_deletion_until_fenced_writer_exits(database, tmp_path, monkeypatch):
    from leroy.db import FileDeletion
    from leroy.engine import finish
    from leroy.maintenance import collect_files, retain

    url, sessions = database
    run_id = install(sessions, retention_runs=1)
    with sessions.begin() as db:
        assignment = claim(db, "test", ["default"], 1)
        db.get(Run, run_id).created_at = now() - timedelta(days=30)
        enqueue(db, db.get(PipelineRow, "test"), {})
    headers = {"Authorization": "Bearer " + assignment["token"]}
    settings = Settings(url, tmp_path, {}, "r" * 40, "admin-password-for-tests", "http://testserver", False)
    path = tmp_path / "logs" / run_id / "work.log"
    writing, release = pause_log_flush(monkeypatch, path)
    with TestClient(create_app(settings)) as client, ThreadPoolExecutor(max_workers=1) as pool:
        upload = pool.submit(client.post, f"/internal/runs/{run_id}/logs/work", headers=headers, content=b"stale")
        try:
            assert writing.wait(3)
            with sessions.begin() as db:
                # Bound the test too: neither completion nor retention may
                # wait for the writer's deliberately paused filesystem call.
                db.execute(text("SET LOCAL lock_timeout = '1s'"))
                finish(db, db.get(Run, run_id), "interrupted", "Lease expired")
            assert retain(sessions, tmp_path) == 1
            assert path.exists()
            with sessions() as db:
                assert db.get(Run, run_id) is None
                assert db.get(FileDeletion, ("logs", run_id)) is not None
        finally:
            release.set()
        assert upload.result(timeout=3).status_code == 409
    collect_files(sessions, tmp_path)
    assert not path.parent.exists()
    with sessions() as db:
        assert db.get(FileDeletion, ("logs", run_id)) is None


def test_log_windows_preserve_utf8_across_pages_and_live_writes(database, tmp_path):
    from leroy.db import StepRow

    url, sessions = database
    run_id = install(sessions)
    content = ("x" * 131071 + "€🙂終了").encode()
    path = tmp_path / "logs" / run_id / "work.log"
    path.parent.mkdir(parents=True)
    path.write_bytes(content)
    with sessions.begin() as db:
        db.get(StepRow, (run_id, "work")).log_bytes = len(content)
    settings = Settings(url, tmp_path, {}, "r" * 40, "admin-password-for-tests", "http://testserver", False)
    with TestClient(create_app(settings)) as client:
        client.post(
            "/api/auth/login",
            headers={"X-Leroy-Request": "1"},
            json={"username": "admin", "password": settings.admin_password},
        ).raise_for_status()
        endpoint = f"/api/runs/{run_id}/logs/work"
        first = client.get(endpoint).json()
        assert first["next_offset"] == 131071
        second = client.get(endpoint, params={"offset": first["next_offset"]}).json()
        assert first["text"] + second["text"] == content.decode()
        assert second["next_offset"] == len(content)
        assert client.get(endpoint, params={"offset": 131072}).json()["text"] == "🙂終了"
        path.write_bytes(b"live \xe2\x82")
        with sessions.begin() as db:
            db.get(StepRow, (run_id, "work")).log_bytes = 7
        assert client.get(endpoint).json() == {"text": "live ", "next_offset": 5}
        with path.open("ab") as stream:
            stream.write(b"\xac")
        with sessions.begin() as db:
            db.get(StepRow, (run_id, "work")).log_bytes = 8
        assert client.get(endpoint, params={"offset": 5}).json() == {"text": "€", "next_offset": 8}
        # Invalid terminal bytes remain visible instead of leaving readers stuck.
        path.write_bytes(b"\xe2")
        with sessions.begin() as db:
            step = db.get(StepRow, (run_id, "work"))
            step.log_bytes, step.status = 1, "failed"
        assert client.get(endpoint).json() == {"text": "\ufffd", "next_offset": 1}


def test_role_boundaries_and_cross_origin_mutations(database, tmp_path):
    from leroy.api import passwords
    from leroy.db import User

    url, sessions = database
    install(sessions)
    settings = Settings(url, tmp_path, {}, "r" * 40, "admin-password-for-tests", "http://testserver", False)
    with sessions.begin() as db:
        for role in ("viewer", "operator"):
            db.add(User(name=role, role=role, password_hash=passwords.hash("test-account-password")))
    with TestClient(create_app(settings)) as client:
        headers = {"X-Leroy-Request": "1"}
        for role in ("viewer", "operator"):
            response = client.post(
                "/api/auth/login",
                headers=headers,
                json={"username": role, "password": "test-account-password"},
            )
            assert response.status_code == 200
            assert client.get("/api/pipelines").status_code == 200
            assert client.post("/api/pipelines/test/runs", headers=headers, json={}).status_code == (
                403 if role == "viewer" else 201
            )
            assert (
                client.post(
                    "/api/pipelines/test/enabled", headers=headers, json={"enabled": True}
                ).status_code
                == 403
            )
            assert (
                client.post(
                    "/api/pipelines/test/runs", headers={**headers, "Origin": "https://foreign.test"}, json={}
                ).status_code
                == 403
            )
            assert client.post("/api/auth/logout", headers=headers).status_code == 200
            assert client.get("/api/runs").status_code == 401


def test_failed_scm_lookup_does_not_starve_other_schedules(database, tmp_path):
    import threading

    from leroy.scheduler import scheduler

    url, sessions = database
    install(sessions, "broken-scm", repository=str(tmp_path / "missing-repository"), poll_seconds=60)
    install(sessions, "scheduled", schedule="* * * * *")
    with sessions.begin() as db:
        for row in db.scalars(select(PipelineRow)):
            row.enabled = True
            row.next_trigger = now() - timedelta(seconds=10)
    settings = Settings(url, tmp_path, {}, "r" * 40, "admin-password-for-tests", "http://testserver", False)

    class OneIteration(threading.Event):
        def wait(self, timeout=None):
            self.set()

    scheduler(sessions, settings, OneIteration())
    with sessions() as db:
        runs = list(db.scalars(select(Run).where(Run.pipeline_id == "scheduled")))
        assert len(runs) == 2 and any(r.trigger == "schedule" for r in runs)
        assert db.get(PipelineRow, "broken-scm").next_trigger < now()


def test_long_queue_cannot_starve_eligible_work(database):
    _, sessions = database
    install(sessions, "blocked", resource="locked", concurrency="parallel")
    with sessions.begin() as db:
        claim(db, "runner", ["default"], 2)
        for _ in range(110):
            enqueue(db, db.get(PipelineRow, "blocked"), {})
    install(sessions, "foreign", profile="other", concurrency="parallel")
    with sessions.begin() as db:
        for _ in range(110):
            enqueue(db, db.get(PipelineRow, "foreign"), {})
    eligible = install(sessions, "eligible")
    with sessions.begin() as db:
        assert claim(db, "runner", ["default"], 2)["id"] == eligible


@pytest.mark.parametrize("expired", [False, True])
def test_timeout_or_lost_parent_cancels_entire_child_tree(database, expired):
    from leroy.db import Event

    _, sessions = database
    parent = install(sessions, concurrency="parallel", timeout=1)
    with sessions.begin() as db:
        claim(db, "runner", ["default"], 4)
        run = db.get(Run, parent)
        run.started_at = now() - timedelta(seconds=10)
        if expired:
            run.lease_until = now() - timedelta(seconds=1)
        child = enqueue(db, db.get(PipelineRow, "test"), {}, parent_id=parent)
        claim(db, "runner", ["default"], 4)
        grandchild = enqueue(db, db.get(PipelineRow, "test"), {}, parent_id=child.id)
        child_id, grandchild_id = child.id, grandchild.id
    for _ in range(2):
        with sessions.begin() as db:
            reconcile(db)
    with sessions() as db:
        assert db.get(Run, child_id).cancel_requested
        assert db.get(Run, grandchild_id).status == "cancelled"
        parent = db.get(Run, parent)
        assert parent.status == "interrupted" if expired else parent.cancel_requested
        if not expired:
            assert (
                len(
                    list(
                        db.scalars(
                            select(Event).where(
                                Event.run_id == parent.id, Event.kind == "run.cancel_requested"
                            )
                        )
                    )
                )
                == 1
            )


def test_child_deduplication_is_per_step_and_invalid_inputs_are_rejected(database, tmp_path):
    url, sessions = database
    parent_id = install(sessions, "parent")
    install(sessions, "child")
    with sessions.begin() as db:
        run = db.get(Run, parent_id)
        spec = dict(run.snapshot)
        spec["steps"] = [
            Step(id=id, name=id, action="child", options={"pipeline": "child"}).model_dump()
            for id in ("first", "second")
        ]
        run.snapshot = spec
        assignment = claim(db, "runner", ["default"], 1)
    settings = Settings(url, tmp_path, {}, "r" * 40, "admin-password-for-tests", "http://testserver", False)
    with TestClient(create_app(settings)) as client:
        headers = {"Authorization": "Bearer " + assignment["token"]}
        endpoint = f"/internal/runs/{parent_id}/children/child"
        first = client.post(endpoint, headers=headers, json={"step_id": "first"}).json()
        assert client.post(endpoint, headers=headers, json={"step_id": "first"}).json()["id"] == first["id"]
        second = client.post(endpoint, headers=headers, json={"step_id": "second"}).json()
        assert second["id"] != first["id"]
        assert client.post(endpoint, headers=headers, json={}).status_code == 403
        assert (
            client.post(
                endpoint, headers=headers, json={"step_id": "first", "parameters": {"bad": 1}}
            ).status_code
            == 422
        )
        assert (
            client.post(endpoint, headers=headers, json={"step_id": "first", "commit": "invalid"}).status_code
            == 422
        )
        response = client.post(f"/internal/runs/{parent_id}/children/{first['id']}/cancel", headers=headers)
        assert response.status_code == 200
        children = client.get(f"/internal/runs/{parent_id}/children", headers=headers).json()
        assert next(c for c in children if c["id"] == first["id"])["status"] == "cancelled"
        client.post(
            "/internal/exited",
            headers={"Authorization": "Bearer " + settings.runner_token},
            json={"runner": "runner", "run_id": parent_id, "exit_code": 0},
        ).raise_for_status()
    with sessions() as db:
        assert db.get(Run, parent_id).status == "failed"
        assert db.get(Run, second["id"]).status == "cancelled"


def test_retention_retries_failed_filesystem_cleanup(database, tmp_path, monkeypatch):
    from pathlib import Path

    from leroy.db import Artifact, FileDeletion
    from leroy.maintenance import retain

    _, sessions = database
    old = install(sessions, retention_runs=1)
    with sessions.begin() as db:
        run = db.get(Run, old)
        run.status, run.created_at = "succeeded", now() - timedelta(days=30)
        item = Artifact(run_id=old, step_id="work", name="report.txt", sha256="a" * 64, size=4)
        db.add(item)
        enqueue(db, db.get(PipelineRow, "test"), {})
        db.flush()
        item_id = item.id
    path = tmp_path / "artifacts" / item_id
    path.parent.mkdir()
    path.write_text("test")
    unlink = Path.unlink
    with monkeypatch.context() as patch:

        def fail(self, *args, **kwargs):
            if self == path:
                raise PermissionError("test injection")
            return unlink(self, *args, **kwargs)

        patch.setattr(Path, "unlink", fail)
        assert retain(sessions, tmp_path) == 1
    with sessions() as db:
        assert db.get(Run, old) is None
        assert db.get(FileDeletion, ("artifacts", item_id)) is not None
    assert path.exists()
    assert retain(sessions, tmp_path) == 0
    assert not path.exists()
    with sessions() as db:
        assert not list(db.scalars(select(FileDeletion)))


def test_event_pagination_includes_latest_and_all_older_step_events(database, tmp_path):
    from leroy.db import Event

    url, sessions = database
    run_id = install(sessions)
    with sessions.begin() as db:
        for i in range(650):
            db.add(Event(run_id=run_id, step_id="work", kind="test", data={"position": i}))
        db.add(Event(run_id=run_id, step_id="other", kind="hidden"))
        db.add(Event(run_id=run_id, kind="run.failed", data={"reason": "latest reason"}))
    settings = Settings(url, tmp_path, {}, "r" * 40, "admin-password-for-tests", "http://testserver", False)
    with TestClient(create_app(settings)) as client:
        client.post(
            "/api/auth/login",
            headers={"X-Leroy-Request": "1"},
            json={"username": "admin", "password": settings.admin_password},
        ).raise_for_status()
        endpoint = f"/api/runs/{run_id}/events?newest=true&step_id=work"
        latest = client.get(endpoint).json()
        assert len(latest) == 500 and latest[0]["kind"] == "run.failed"
        older = client.get(endpoint + f"&before={latest[-1]['id']}").json()
        assert len(older) == 152
        assert len({e["id"] for e in latest + older}) == 652
        assert not any(e["kind"] == "hidden" for e in latest + older)


def test_account_administration_revokes_sessions_and_preserves_an_admin(database):
    from pwdlib import PasswordHash

    from leroy.accounts import manage_account
    from leroy.db import Session, User

    _, sessions = database
    manage_account(sessions, "add", "admin", role="admin", password="test-password-before")
    with sessions.begin() as db:
        db.add(Session(id="s" * 64, user="admin", expires=now() + timedelta(hours=1)))
    manage_account(sessions, "password", "admin", password="test-password-after")
    with sessions() as db:
        assert not list(db.scalars(select(Session)))
        assert PasswordHash.recommended().verify("test-password-after", db.get(User, "admin").password_hash)
    with pytest.raises(ValueError, match="last administrator"):
        manage_account(sessions, "role", "admin", role="viewer")
    manage_account(sessions, "add", "viewer", role="viewer", password="test-viewer-password")
    with sessions.begin() as db:
        db.add(Session(id="v" * 64, user="viewer", expires=now() + timedelta(hours=1)))
    manage_account(sessions, "role", "viewer", role="operator")
    with sessions() as db:
        assert db.get(User, "viewer").role == "operator"
        assert not list(db.scalars(select(Session)))
    manage_account(sessions, "delete", "viewer")
    with sessions() as db:
        assert db.get(User, "viewer") is None


def test_interrupted_uploads_are_reclaimed_only_after_the_attempt_ends(database, tmp_path):
    from leroy.db import FileDeletion, uid
    from leroy.maintenance import collect_files

    _, sessions = database
    run_id = install(sessions)
    item_id = uid()
    path = tmp_path / "artifacts" / item_id
    path.parent.mkdir()
    path.write_text("partial upload")
    with sessions.begin() as db:
        claim(db, "runner", ["default"], 1)
        db.add(FileDeletion(kind="artifacts", id=item_id, upload_run_id=run_id))
    collect_files(sessions, tmp_path)
    assert path.exists()
    with sessions.begin() as db:
        db.get(Run, run_id).lease_until = now() - timedelta(seconds=1)
    with sessions.begin() as db:
        reconcile(db)
    collect_files(sessions, tmp_path)
    assert not path.exists()
    with sessions() as db:
        assert db.get(FileDeletion, ("artifacts", item_id)) is None


def test_cancellation_refreshes_state_after_a_concurrent_completion(database):
    from leroy.engine import finish

    _, sessions = database
    id = install(sessions)
    with sessions.begin() as stale:
        original = stale.get(Run, id)
        assert original.status == "queued"
        with sessions.begin() as other:
            claim(other, "runner", ["default"], 1)
            finish(other, other.get(Run, id), "succeeded")
        request_cancel(stale, original, "Concurrent cancellation")
    with sessions() as db:
        run = db.get(Run, id)
        assert run.status == "succeeded" and not run.cancel_requested

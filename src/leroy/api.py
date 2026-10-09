import asyncio
import codecs
import hashlib
import json
import logging
import secrets
import threading
import time
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

from fastapi import Body, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pwdlib import PasswordHash
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text

from .config import Settings
from .db import (
    Artifact,
    Event,
    FileDeletion,
    PipelineRow,
    Run,
    RunnerRow,
    Session,
    StepRow,
    User,
    connect,
    lock_log_files,
    now,
    uid,
)
from .engine import (
    cancel_children,
    claim,
    digest,
    enqueue,
    event,
    finish,
    reconcile,
    request_cancel,
    serialise,
    validate_child_call,
)
from .schema import TERMINAL, Pipeline

log = logging.getLogger("leroy")
passwords = PasswordHash.recommended()


def create_app(settings=None):
    settings = settings or Settings.load()
    engine, sessions = connect(settings.database_url)
    settings.data.mkdir(parents=True, exist_ok=True)
    stop = threading.Event()

    @asynccontextmanager
    async def lifespan(app):
        from .catalog import catalog
        from .scheduler import scheduler

        if len(settings.runner_token) < 32 or len(settings.admin_password) < 16:
            raise RuntimeError("Set strong runner and administrator credentials before startup")
        with sessions.begin() as db:
            if db.get(User, "admin") is None:
                db.add(User(name="admin", password_hash=passwords.hash(settings.admin_password)))
            for pipeline in catalog(settings.config):
                row = db.get(PipelineRow, pipeline.id)
                if row is None:
                    db.add(PipelineRow(id=pipeline.id, spec=pipeline.model_dump(), enabled=pipeline.enabled))
        thread = threading.Thread(target=scheduler, args=(sessions, settings, stop), daemon=True)
        thread.start()
        yield
        stop.set()
        thread.join(timeout=5)
        engine.dispose()

    app = FastAPI(title="Leroy", version="0.1.0", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.sessions, app.state.settings = sessions, settings

    @app.middleware("http")
    async def security_headers(request, call_next):
        if request.method not in ("GET", "HEAD", "OPTIONS") and not request.url.path.startswith("/internal/"):
            origin = request.headers.get("origin")
            if (origin and origin != settings.origin) or request.headers.get("x-leroy-request") != "1":
                return Response("Invalid request origin", status_code=403)
        response = await call_next(request)
        response.headers.update(
            {
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "same-origin",
                "X-Frame-Options": "DENY",
                "Cache-Control": "no-store",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'",
            }
        )
        return response

    def user(request: Request):
        cookie = request.cookies.get("leroy_session", "")
        with sessions() as db:
            session = db.get(Session, digest(cookie))
            if not session or session.expires < now():
                raise HTTPException(401, "Please sign in")
            account = db.get(User, session.user)
            if account is None:
                raise HTTPException(401, "Please sign in")
            return {"name": account.name, "role": account.role}

    def operator(account=Depends(user)):
        if account["role"] not in ("admin", "operator"):
            raise HTTPException(403, "Operator role required")
        return account

    def admin(account=Depends(user)):
        if account["role"] != "admin":
            raise HTTPException(403, "Administrator role required")
        return account

    def runner(request: Request):
        if not secrets.compare_digest(
            request.headers.get("authorization", ""), "Bearer " + settings.runner_token
        ):
            raise HTTPException(401, "Runner authentication required")

    def owned(db, run_id, request, *, lock=True):
        run = (
            db.scalar(select(Run).where(Run.id == run_id).with_for_update()) if lock else db.get(Run, run_id)
        )
        token = request.headers.get("authorization", "").removeprefix("Bearer ")
        if (
            not run
            or not run.token_hash
            or not secrets.compare_digest(digest(token), run.token_hash)
            or run.status not in ("running", "waiting")
            or not run.lease_until
            or run.lease_until < now()
        ):
            raise HTTPException(409, "Attempt no longer owns this run")
        return run

    def get_run(db, run_id):
        run = db.get(Run, run_id)
        if run is None:
            raise HTTPException(404, "Run not found")
        return run

    @app.get("/health/live")
    def live():
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready():
        with sessions() as db:
            db.execute(text("SELECT 1"))
        return {"status": "ok"}

    class Login(BaseModel):
        username: str = Field(max_length=100)
        password: str = Field(max_length=1024)

    @app.post("/api/auth/login")
    def login(body: Login, response: Response):
        with sessions.begin() as db:
            # Bound expensive password checks without queuing unauthenticated
            # requests on the DB pool used by job heartbeats and the scheduler.
            if not db.scalar(text("SELECT pg_try_advisory_xact_lock(7046102)")):
                raise HTTPException(429, "Sign-in busy; please retry", headers={"Retry-After": "1"})
            account = db.get(User, body.username)
            if not account or not passwords.verify(body.password, account.password_hash):
                time.sleep(0.25)
                raise HTTPException(401, "Invalid username or password")
            token = secrets.token_urlsafe(40)
            db.add(Session(id=digest(token), user=account.name, expires=now() + timedelta(hours=12)))
            response.set_cookie(
                "leroy_session",
                token,
                httponly=True,
                secure=settings.cookie_secure,
                samesite="strict",
                max_age=43200,
            )
            return {"name": account.name, "role": account.role}

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response, account=Depends(user)):
        with sessions.begin() as db:
            session = db.get(Session, digest(request.cookies.get("leroy_session", "")))
            if session:
                db.delete(session)
        response.delete_cookie("leroy_session")
        return {"ok": True}

    @app.get("/api/auth/me")
    def me(account=Depends(user)):
        return account

    @app.get("/api/pipelines")
    def pipelines(account=Depends(user)):
        with sessions() as db:
            result = []
            for row in db.scalars(select(PipelineRow).order_by(PipelineRow.id)):
                last = db.scalar(
                    select(Run).where(Run.pipeline_id == row.id).order_by(Run.number.desc()).limit(1)
                )
                result.append(
                    dict(
                        id=row.id,
                        spec=row.spec,
                        enabled=row.enabled,
                        revision=row.revision,
                        last_run=serialise(last) if last else None,
                    )
                )
            return result

    @app.put("/api/pipelines/{pipeline_id}")
    def publish(pipeline_id: str, spec: Pipeline, account=Depends(admin)):
        if pipeline_id != spec.id:
            raise HTTPException(400, "Pipeline ID mismatch")
        with sessions.begin() as db:
            db.execute(text("SELECT pg_advisory_xact_lock(7046101)"))
            row = db.get(PipelineRow, pipeline_id)
            if row:
                row.spec, row.revision, row.enabled, row.updated_at = (
                    spec.model_dump(),
                    row.revision + 1,
                    spec.enabled,
                    now(),
                )
                row.next_trigger = None
            else:
                db.add(PipelineRow(id=spec.id, spec=spec.model_dump(), enabled=spec.enabled))
            event(db, None, "pipeline.published", {"pipeline": spec.id, "actor": account["name"]})
        return {"id": spec.id}

    @app.post("/api/pipelines/{pipeline_id}/enabled")
    def enable(pipeline_id: str, enabled: bool = Body(embed=True), account=Depends(admin)):
        with sessions.begin() as db:
            db.execute(text("SELECT pg_advisory_xact_lock(7046101)"))
            row = db.get(PipelineRow, pipeline_id)
            if not row:
                raise HTTPException(404)
            row.enabled = enabled
            row.next_trigger = None
            event(
                db,
                None,
                "pipeline.enabled",
                {"pipeline": pipeline_id, "enabled": enabled, "actor": account["name"]},
            )
        return {"enabled": enabled}

    class Start(BaseModel):
        parameters: dict = Field(default_factory=dict)
        commit: str | None = Field(default=None, pattern=r"^[a-f0-9]{40,64}$")

    @app.post("/api/pipelines/{pipeline_id}/runs", status_code=201)
    def start(pipeline_id: str, body: Start, account=Depends(operator)):
        with sessions.begin() as db:
            row = db.get(PipelineRow, pipeline_id)
            if not row:
                raise HTTPException(404, "Pipeline not found")
            try:
                run = enqueue(db, row, body.parameters, actor=account["name"], commit=body.commit)
            except ValueError as error:
                raise HTTPException(422, str(error)) from error
            return serialise(run)

    @app.get("/api/runs")
    def runs(
        pipeline: str | None = None,
        status: str | None = None,
        before: int | None = None,
        limit: int = 50,
        account=Depends(user),
    ):
        with sessions() as db:
            query = select(Run).order_by(Run.number.desc()).limit(max(1, min(limit, 200)))
            if pipeline:
                query = query.where(Run.pipeline_id == pipeline)
            if status:
                query = query.where(Run.status == status)
            if before:
                query = query.where(Run.number < before)
            return [serialise(r) for r in db.scalars(query)]

    @app.get("/api/runs/{run_id}")
    def detail(run_id: str, account=Depends(user)):
        with sessions() as db:
            result = serialise(get_run(db, run_id))
            result["steps"] = [
                serialise(s)
                for s in db.scalars(
                    select(StepRow).where(StepRow.run_id == run_id).order_by(StepRow.position)
                )
            ]
            result["artifacts"] = [
                serialise(a) for a in db.scalars(select(Artifact).where(Artifact.run_id == run_id))
            ]
            result["children"] = [
                serialise(r)
                for r in db.scalars(select(Run).where(Run.parent_id == run_id).order_by(Run.number))
            ]
            return result

    @app.post("/api/runs/{run_id}/cancel")
    def cancel(run_id: str, account=Depends(operator)):
        with sessions.begin() as db:
            request_cancel(db, get_run(db, run_id), "Cancelled by " + account["name"])
        return {"ok": True}

    @app.post("/api/runs/{run_id}/retry", status_code=201)
    def retry(run_id: str, account=Depends(operator)):
        with sessions.begin() as db:
            old = get_run(db, run_id)
            if old.status not in TERMINAL:
                raise HTTPException(409, "Only finished runs can be repeated")
            run = enqueue(
                db,
                db.get(PipelineRow, old.pipeline_id),
                old.parameters,
                actor=account["name"],
                trigger="retry",
                commit=old.commit,
                retry_of=old.id,
                snapshot=old.snapshot,
            )
            return serialise(run)

    @app.get("/api/runs/{run_id}/events")
    def events(
        run_id: str,
        after: int = 0,
        before: int | None = None,
        newest: bool = False,
        step_id: str | None = None,
        account=Depends(user),
    ):
        with sessions() as db:
            get_run(db, run_id)
            query = select(Event).where(Event.run_id == run_id, Event.id > after)
            if before is not None:
                query = query.where(Event.id < before)
            if step_id is not None:
                query = query.where((Event.step_id == step_id) | Event.step_id.is_(None))
            return [
                serialise(e)
                for e in db.scalars(query.order_by(Event.id.desc() if newest else Event.id).limit(500))
            ]

    @app.get("/api/runs/{run_id}/stream")
    async def stream(run_id: str, request: Request, after: int = 0, account=Depends(user)):
        with sessions() as db:
            get_run(db, run_id)
        try:
            cursor = max(after, int(request.headers.get("last-event-id", "0")))
        except ValueError:
            raise HTTPException(400, "Invalid event cursor") from None

        async def generate():
            nonlocal cursor

            def read():
                try:
                    user(request)
                except HTTPException:
                    return None
                with sessions() as db:
                    return [
                        serialise(e)
                        for e in db.scalars(
                            select(Event)
                            .where(Event.run_id == run_id, Event.id > cursor)
                            .order_by(Event.id)
                            .limit(100)
                        )
                    ]

            while not await request.is_disconnected():
                rows = await asyncio.to_thread(read)
                if rows is None:
                    yield "event: session-expired\ndata: {}\n\n"
                    return
                for row in rows:
                    cursor = row["id"]
                    yield f"id: {cursor}\ndata: {json.dumps(row)}\n\n"
                if not rows:
                    yield ": heartbeat\n\n"
                await asyncio.sleep(1)

        return StreamingResponse(
            generate(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"}
        )

    @app.get("/api/runs/{run_id}/logs/{step_id}")
    def logs(run_id: str, step_id: str, offset: int = 0, account=Depends(user)):
        with sessions() as db:
            step = db.get(StepRow, (run_id, step_id))
            if not step:
                raise HTTPException(404)
            committed = step.log_bytes
            finished = step.status in TERMINAL
        path = settings.data / "logs" / run_id / (step_id + ".log")
        data = b""
        if path.exists():
            with path.open("rb") as f:
                f.seek(max(0, offset))
                data = f.read(min(131072, max(0, committed - max(0, offset))))
        next_offset = max(0, offset) + len(data)
        # A tail window can begin inside a multibyte character. Skip only that
        # partial leading character, and carry an incomplete ending to the next
        # byte-offset read instead of displaying permanent replacement glyphs.
        if offset > 0:
            data = data.lstrip(bytes(range(0x80, 0xC0)))
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        decoded = decoder.decode(data, final=finished and next_offset >= committed)
        pending, _ = decoder.getstate()
        return {"text": decoded, "next_offset": next_offset - len(pending)}

    @app.get("/api/runs/{run_id}/logs/{step_id}/download")
    def download_log(run_id: str, step_id: str, account=Depends(user)):
        with sessions() as db:
            step = db.get(StepRow, (run_id, step_id))
            if not step:
                raise HTTPException(404)
            size = step.log_bytes
        path = settings.data / "logs" / run_id / (step_id + ".log")

        def chunks():
            remaining = size
            if path.exists():
                with path.open("rb") as handle:
                    while remaining > 0:
                        data = handle.read(min(remaining, 65536))
                        if not data:
                            break
                        remaining -= len(data)
                        yield data

        return StreamingResponse(
            chunks(),
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{step_id}.log"'},
        )

    @app.get("/api/artifacts/{artifact_id}")
    def artifact(artifact_id: str, account=Depends(user)):
        with sessions() as db:
            item = db.get(Artifact, artifact_id)
            if not item:
                raise HTTPException(404)
            return FileResponse(
                settings.data / "artifacts" / item.id,
                media_type="application/octet-stream",
                filename=Path(item.name).name,
            )

    @app.get("/api/runners")
    def runners(account=Depends(user)):
        with sessions() as db:
            return [
                dict(serialise(r), online=(now() - r.last_seen).total_seconds() < 30)
                for r in db.scalars(select(RunnerRow))
            ]

    @app.get("/api/system")
    def system(account=Depends(user)):
        with sessions() as db:
            counts = dict(db.execute(select(Run.status, func.count()).group_by(Run.status)).all())
        return {
            "version": "0.1.0",
            "storage": "filesystem",
            "database": "PostgreSQL",
            "counts": counts,
            "origin": settings.origin,
            "timezone": "Europe/Berlin",
        }

    class Claim(BaseModel):
        runner: str = Field(pattern=r"^[a-zA-Z0-9_.-]{1,100}$")
        profiles: list[str]
        capacity: int = Field(ge=1, le=32)

    @app.post("/internal/claim", dependencies=[Depends(runner)])
    def acquire(body: Claim):
        with sessions.begin() as db:
            db.execute(text("SELECT pg_advisory_xact_lock(7046101)"))
            reconcile(db)
            return claim(db, body.runner, body.profiles, body.capacity)

    class Reap(BaseModel):
        runner: str = Field(max_length=100)
        run_ids: list[str] = Field(max_length=100)

    @app.post("/internal/reap", dependencies=[Depends(runner)])
    def reap(body: Reap):
        with sessions() as db:
            return [
                r.id
                for r in db.scalars(
                    select(Run).where(
                        Run.id.in_(body.run_ids), Run.runner == body.runner, Run.status.in_(TERMINAL)
                    )
                )
            ]

    class Exited(BaseModel):
        runner: str = Field(max_length=100)
        run_id: str = Field(pattern=r"^[a-f0-9]{32}$")
        exit_code: int

    @app.post("/internal/exited", dependencies=[Depends(runner)])
    def exited(body: Exited):
        with sessions.begin() as db:
            db.execute(text("SELECT pg_advisory_xact_lock(7046101)"))
            run = db.scalar(select(Run).where(Run.id == body.run_id).with_for_update())
            if run and run.runner == body.runner and run.status in ("running", "waiting"):
                reason = f"Job container exited with code {body.exit_code} without completing its report"
                cancel_children(db, run, "Parent job container exited")
                status = "failed"
                if run.cancel_requested:
                    status = "timed_out" if "timeout" in run.reason.lower() else "cancelled"
                    reason = run.reason
                finish(db, run, status, reason)
        return {"ok": True}

    @app.post("/internal/runs/{run_id}/heartbeat")
    def heartbeat(run_id: str, request: Request):
        with sessions.begin() as db:
            run = owned(db, run_id, request)
            run.lease_until = now() + timedelta(seconds=90)
            return {"cancel": run.cancel_requested, "reason": run.reason}

    @app.post("/internal/runs/{run_id}/identity")
    def identity(run_id: str, request: Request, values: dict = Body()):
        with sessions.begin() as db:
            run = owned(db, run_id, request)
            commit = values.get("commit")
            if commit:
                import re

                if not re.fullmatch(r"[a-f0-9]{40,64}", commit) or (run.commit and run.commit != commit):
                    raise HTTPException(409, "Checkout identity differs from requested revision")
                run.commit = commit
            if values.get("image_digest"):
                run.image_digest = str(values["image_digest"])[:100]
            event(db, run.id, "run.identity", values)
        return {"ok": True}

    @app.post("/internal/runs/{run_id}/waiting")
    def waiting(run_id: str, request: Request, values: dict = Body()):
        with sessions.begin() as db:
            db.execute(text("SELECT pg_advisory_xact_lock(7046101)"))
            run = owned(db, run_id, request)
            wait = bool(values.get("waiting"))
            if not wait:
                worker = db.get(RunnerRow, run.runner)
                active = db.scalar(
                    select(func.count())
                    .select_from(Run)
                    .where(Run.runner == run.runner, Run.status == "running")
                )
                if run.status == "waiting" and worker and active >= worker.capacity:
                    return {"resumed": False}
            run.status = "waiting" if wait else "running"
            event(
                db,
                run.id,
                "run." + run.status,
                {"reason": "Waiting for child pipeline" if wait else "Child completed"},
            )
            return {"resumed": True}

    @app.post("/internal/runs/{run_id}/steps/{step_id}")
    def update_step(run_id: str, step_id: str, request: Request, values: dict = Body()):
        with sessions.begin() as db:
            run = owned(db, run_id, request)
            step = db.get(StepRow, (run_id, step_id))
            if not step:
                raise HTTPException(404)
            status = values.get("status")
            if status not in TERMINAL | {"running"}:
                raise HTTPException(422, "Invalid step state")
            if step.status in TERMINAL:
                if step.status == status:
                    return {"ok": True}
                raise HTTPException(409, "Step already finished")
            if status == "running" and step.status == "pending":
                step.started_at = now()
            step.status, step.reason = status, str(values.get("reason", ""))[:4000]
            step.outputs = values.get("outputs", {})
            step.exit_code = values.get("exit_code")
            if status in TERMINAL:
                step.finished_at = now()
            event(db, run.id, "step." + status, {"reason": step.reason}, step.id)
        return {"ok": True}

    @app.post("/internal/runs/{run_id}/logs/{step_id}")
    async def append_log(run_id: str, step_id: str, request: Request, offset: int = 0):
        data = bytearray()
        async for part in request.stream():
            data.extend(part)
            if len(data) > 65536:
                raise HTTPException(413, "Log chunk too large")

        def append():
            with sessions.begin() as db:
                owned(db, run_id, request, lock=False)
                lock_log_files(db, run_id)
                # A retry may have waited for an earlier disk write. Recheck
                # its ownership and offset using the current committed state.
                db.expire_all()
                owned(db, run_id, request, lock=False)
                step = db.get(StepRow, (run_id, step_id))
                if not step:
                    raise HTTPException(404)
                if step.log_bytes > 64 * 1024 * 1024:
                    raise HTTPException(413, "Step log limit reached")
                if offset != step.log_bytes:
                    return {"offset": step.log_bytes}
                path = settings.data / "logs" / run_id / (step_id + ".log")
                path.parent.mkdir(parents=True, exist_ok=True)
                # Database offset is authoritative after a crash between file write and commit.
                with path.open("r+b" if path.exists() else "w+b") as f:
                    f.truncate(offset)
                    f.seek(offset)
                    f.write(data)
                    f.flush()
                    __import__("os").fsync(f.fileno())
                # Slow I/O must not block this run's heartbeat. Fence again
                # before publishing bytes; interrupted writes remain beyond
                # the authoritative offset and the next append truncates them.
                db.expire_all()
                owned(db, run_id, request)
                step = db.get(StepRow, (run_id, step_id))
                step.log_bytes += len(data)
                event(db, run_id, "log.updated", {"bytes": step.log_bytes}, step_id)
                return {"offset": step.log_bytes}

        return await asyncio.to_thread(append)

    @app.post("/internal/runs/{run_id}/artifacts/{step_id}")
    async def upload(run_id: str, step_id: str, request: Request, name: str):
        if len(name) > 400:
            raise HTTPException(422)
        item_id, size, checksum = uid(), 0, hashlib.sha256()

        def register():
            with sessions.begin() as db:
                owned(db, run_id, request)
                if not db.get(StepRow, (run_id, step_id)):
                    raise HTTPException(404)
                db.add(FileDeletion(kind="artifacts", id=item_id, upload_run_id=run_id))

        # PostgreSQL locks and commits must not block the ASGI event loop:
        # other runs still need to renew their leases while this upload waits.
        await asyncio.to_thread(register)
        directory = settings.data / "artifacts"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / item_id
        try:
            with path.open("xb") as f:
                async for part in request.stream():
                    size += len(part)
                    if size > 512 * 1024 * 1024:
                        raise HTTPException(413, "Artifact limit is 512 MiB")
                    checksum.update(part)
                    await asyncio.to_thread(f.write, part)
                await asyncio.to_thread(f.flush)
                await asyncio.to_thread(__import__("os").fsync, f.fileno())
        except BaseException:
            path.unlink(missing_ok=True)
            raise

        def publish():
            try:
                with sessions.begin() as db:
                    owned(db, run_id, request)
                    item = Artifact(
                        id=item_id,
                        run_id=run_id,
                        step_id=step_id,
                        name=name,
                        sha256=checksum.hexdigest(),
                        size=size,
                    )
                    db.add(item)
                    db.delete(db.get(FileDeletion, ("artifacts", item_id)))
                    event(db, run_id, "artifact.created", {"id": item_id, "name": name}, step_id)
            except BaseException:
                path.unlink(missing_ok=True)
                raise

        # Once publication starts, its thread owns cleanup as well. Cancelling
        # the request must not unlink a file whose database commit still runs.
        await asyncio.to_thread(publish)
        return {"id": item_id}

    @app.post("/internal/runs/{run_id}/complete")
    def complete(run_id: str, request: Request, values: dict = Body()):
        with sessions.begin() as db:
            db.execute(text("SELECT pg_advisory_xact_lock(7046101)"))
            run = owned(db, run_id, request)
            status = values.get("status")
            if status not in TERMINAL:
                raise HTTPException(422)
            steps = list(db.scalars(select(StepRow).where(StepRow.run_id == run_id)))
            if status == "succeeded" and any(s.status not in ("succeeded", "skipped") for s in steps):
                raise HTTPException(409, "Required steps have not succeeded")
            reason = str(values.get("reason", run.reason))[:4000]
            if run.cancel_requested:
                status = "timed_out" if "timeout" in run.reason.lower() else "cancelled"
                # Completion may race the worker's next heartbeat. Preserve the
                # authoritative cause instead of replacing it with a process exit.
                reason = run.reason
            if status != "succeeded":
                cancel_children(db, run, "Parent run ended: " + status)
            run.outputs = values.get("outputs", {})
            finish(db, run, status, reason)
        return {"ok": True}

    @app.post("/internal/runs/{run_id}/children/{pipeline_id}")
    def child(run_id: str, pipeline_id: str, request: Request, values: dict = Body()):
        with sessions.begin() as db:
            db.execute(text("SELECT pg_advisory_xact_lock(7046101)"))
            parent = owned(db, run_id, request)
            allowed = [
                s
                for s in parent.snapshot["steps"]
                if s["action"] == "child" and s.get("options", {}).get("pipeline") == pipeline_id
            ]
            step_id = values.get("step_id")
            # Legacy workers omitted the step ID; accept that only when unambiguous.
            if step_id is None and len(allowed) == 1:
                step_id = allowed[0]["id"]
            if not any(s["id"] == step_id for s in allowed) or parent.cancel_requested:
                raise HTTPException(403)
            row = db.get(PipelineRow, pipeline_id)
            if not row:
                raise HTTPException(404)
            try:
                bound = Start.model_validate(values)
                existing = db.scalar(select(Run).where(Run.dedupe_key == f"child:{run_id}:{step_id}"))
                child_spec = Pipeline.model_validate(existing.snapshot if existing else row.spec)
                child_spec.bind(bound.parameters)
                if existing is not None:
                    return serialise(existing)
                step = next(s for s in allowed if s["id"] == step_id)
                validate_child_call(db, parent, step, child_spec)
                child_run = enqueue(
                    db,
                    row,
                    bound.parameters,
                    parent_id=run_id,
                    trigger="pipeline",
                    actor=parent.actor,
                    commit=bound.commit,
                    dedupe_key=f"child:{run_id}:{step_id}",
                )
            except ValueError as error:
                raise HTTPException(422, str(error)) from error
            return serialise(child_run)

    @app.get("/internal/runs/{run_id}/children")
    def child_states(run_id: str, request: Request):
        with sessions() as db:
            owned(db, run_id, request, lock=False)
            return [serialise(r) for r in db.scalars(select(Run).where(Run.parent_id == run_id))]

    @app.post("/internal/runs/{run_id}/children/{child_id}/cancel")
    def cancel_child(run_id: str, child_id: str, request: Request):
        with sessions.begin() as db:
            db.execute(text("SELECT pg_advisory_xact_lock(7046101)"))
            owned(db, run_id, request)
            target = get_run(db, child_id)
            if target.parent_id != run_id:
                raise HTTPException(403)
            request_cancel(db, target, "Parent step timeout exceeded")
        return {"ok": True}

    static = Path(__import__("os").getenv("LEROY_WEB", "/app/web/dist"))
    if static.exists():
        app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

        @app.get("/{path:path}")
        def frontend(path: str):
            if path.startswith(("api/", "internal/", "health/")):
                raise HTTPException(404)
            return FileResponse(static / "index.html")

    return app

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    create_engine,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def now():
    return datetime.now(timezone.utc)


def uid():
    return uuid.uuid4().hex


def lock_log_files(db, run_id, *, wait=True):
    """Serialize log I/O and deletion without holding the run's lease row lock."""
    function = "pg_advisory_xact_lock" if wait else "pg_try_advisory_xact_lock"
    result = db.scalar(text(f"SELECT {function}(7046102, hashtext(:run_id))"), {"run_id": run_id})
    return True if wait else result


class Base(DeclarativeBase):
    pass


class PipelineRow(Base):
    __tablename__ = "pipelines"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    spec: Mapped[dict] = mapped_column(JSONB)
    revision: Mapped[int] = mapped_column(default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    last_revision: Mapped[str | None] = mapped_column(String(64))
    next_trigger: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    number: Mapped[int] = mapped_column(
        BigInteger,
        autoincrement=True,
        unique=True,
        server_default=__import__("sqlalchemy").text("nextval('run_number_seq')"),
    )
    pipeline_id: Mapped[str] = mapped_column(ForeignKey("pipelines.id"), index=True)
    snapshot: Mapped[dict] = mapped_column(JSONB)
    parameters: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    trigger: Mapped[str] = mapped_column(String(120), default="manual")
    actor: Mapped[str] = mapped_column(String(100), default="system")
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("runs.id"), index=True)
    retry_of: Mapped[str | None] = mapped_column(ForeignKey("runs.id"))
    commit: Mapped[str | None] = mapped_column(String(64))
    image_digest: Mapped[str | None] = mapped_column(String(100))
    runner: Mapped[str | None] = mapped_column(String(100))
    token_hash: Mapped[str | None] = mapped_column(String(64))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    cancel_requested: Mapped[bool] = mapped_column(default=False)
    resource: Mapped[str | None] = mapped_column(String(200), index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    outputs: Mapped[dict] = mapped_column(JSONB, default=dict)
    dedupe_key: Mapped[str | None] = mapped_column(String(200), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StepRow(Base):
    __tablename__ = "steps"
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True)
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    position: Mapped[int] = mapped_column(Integer)
    needs: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    reason: Mapped[str] = mapped_column(Text, default="")
    exit_code: Mapped[int | None] = mapped_column(Integer)
    outputs: Mapped[dict] = mapped_column(JSONB, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    log_bytes: Mapped[int] = mapped_column(BigInteger, default=0)


class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    step_id: Mapped[str | None] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(50))
    data: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (Index("events_run_cursor", "run_id", "id"),)


class Artifact(Base):
    __tablename__ = "artifacts"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    step_id: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(400))
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class User(Base):
    __tablename__ = "users"
    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20), default="admin")


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user: Mapped[str] = mapped_column(ForeignKey("users.name"))
    expires: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RunnerRow(Base):
    __tablename__ = "runners"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    profiles: Mapped[list] = mapped_column(JSONB, default=list)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    capacity: Mapped[int] = mapped_column(default=1)


class FileDeletion(Base):
    __tablename__ = "file_deletions"
    kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    upload_run_id: Mapped[str | None] = mapped_column(String(32))


def connect(url):
    engine = create_engine(
        url, pool_size=10, max_overflow=5, pool_pre_ping=True, connect_args={"connect_timeout": 10}
    )
    return engine, sessionmaker(engine, expire_on_commit=False)

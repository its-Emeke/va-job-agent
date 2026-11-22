"""Database layer via SQLAlchemy Core.

One codebase, two backends:
- local dev  -> SQLite file (DATABASE_URL defaults to sqlite:///jobs.db)
- Vercel     -> Postgres (DATABASE_URL = postgresql+psycopg://...)

Gmail OAuth tokens are stored per-user in the DB (the filesystem is ephemeral
on serverless, so a token file would not survive).
"""
from datetime import datetime, timezone

from sqlalchemy import (
    MetaData, Table, Column, Integer, String, Text, UniqueConstraint,
    create_engine, insert, select, update, func,
)

from .config import DATABASE_URL

# SQLite needs check_same_thread off for the dev server's threadpool.
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=_connect_args)
IS_SQLITE = engine.dialect.name == "sqlite"

metadata = MetaData()

users = Table(
    "users", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("email", String(320), unique=True, nullable=False),
    Column("name", String(200)),
    Column("gmail_token", Text),          # JSON string of OAuth creds
    Column("created_at", String(40), nullable=False),
)

jobs = Table(
    "jobs", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, nullable=False, index=True),
    Column("source", String(40), nullable=False),
    Column("external_id", String(200), nullable=False),
    Column("title", String(500), nullable=False),
    Column("company", String(300)),
    Column("location", String(300)),
    Column("url", Text),
    Column("contact_email", String(320)),
    Column("description", Text),
    Column("posted_at", String(40)),
    Column("fetched_at", String(40), nullable=False),
    Column("status", String(20), nullable=False, default="new"),
    Column("draft_subject", Text),
    Column("draft_body", Text),
    Column("sent_at", String(40)),
    UniqueConstraint("user_id", "source", "external_id", name="uq_job_identity"),
)


def init_db():
    metadata.create_all(engine)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------- users ----------------

def get_or_create_user(email: str, name: str | None) -> dict:
    email = email.lower()
    with engine.begin() as conn:
        row = conn.execute(select(users).where(users.c.email == email)).mappings().first()
        if row:
            return dict(row)
        conn.execute(insert(users).values(email=email, name=name, created_at=now_iso()))
        row = conn.execute(select(users).where(users.c.email == email)).mappings().first()
        return dict(row)


def save_gmail_token(user_id: int, token_json: str):
    with engine.begin() as conn:
        conn.execute(update(users).where(users.c.id == user_id).values(gmail_token=token_json))


def get_gmail_token(user_id: int) -> str | None:
    with engine.connect() as conn:
        row = conn.execute(
            select(users.c.gmail_token).where(users.c.id == user_id)
        ).first()
        return row[0] if row and row[0] else None


# ---------------- jobs ----------------

def upsert_job(job: dict, user_id: int) -> bool:
    """Insert if new for this user. Returns True if inserted."""
    values = dict(
        user_id=user_id,
        source=job["source"],
        external_id=str(job["external_id"]),
        title=job["title"],
        company=job.get("company"),
        location=job.get("location"),
        url=job.get("url"),
        contact_email=job.get("contact_email"),
        description=job.get("description"),
        posted_at=job.get("posted_at"),
        fetched_at=now_iso(),
        status="new",
    )
    if IS_SQLITE:
        from sqlalchemy.dialects.sqlite import insert as dialect_insert
    else:
        from sqlalchemy.dialects.postgresql import insert as dialect_insert
    stmt = dialect_insert(jobs).values(**values).on_conflict_do_nothing(
        index_elements=["user_id", "source", "external_id"]
    )
    with engine.begin() as conn:
        result = conn.execute(stmt)
        return (result.rowcount or 0) > 0


def list_jobs(user_id: int, status: str | None = None, limit: int = 200) -> list[dict]:
    q = select(jobs).where(jobs.c.user_id == user_id)
    if status:
        q = q.where(jobs.c.status == status)
    q = q.order_by(func.coalesce(jobs.c.posted_at, jobs.c.fetched_at).desc()).limit(limit)
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(q).mappings().all()]


def get_job(job_id: int, user_id: int) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(
            select(jobs).where(jobs.c.id == job_id, jobs.c.user_id == user_id)
        ).mappings().first()
        return dict(row) if row else None


def save_draft(job_id: int, user_id: int, subject: str, body: str):
    with engine.begin() as conn:
        conn.execute(
            update(jobs).where(jobs.c.id == job_id, jobs.c.user_id == user_id)
            .values(draft_subject=subject, draft_body=body, status="drafted")
        )


def set_status(job_id: int, user_id: int, status: str):
    with engine.begin() as conn:
        conn.execute(
            update(jobs).where(jobs.c.id == job_id, jobs.c.user_id == user_id).values(status=status)
        )


def mark_sent(job_id: int, user_id: int):
    with engine.begin() as conn:
        conn.execute(
            update(jobs).where(jobs.c.id == job_id, jobs.c.user_id == user_id)
            .values(status="sent", sent_at=now_iso())
        )


def sent_today_count(user_id: int) -> int:
    today = now_iso()[:10]
    with engine.connect() as conn:
        return conn.execute(
            select(func.count()).select_from(jobs).where(
                jobs.c.user_id == user_id,
                jobs.c.status == "sent",
                func.substr(jobs.c.sent_at, 1, 10) == today,
            )
        ).scalar() or 0

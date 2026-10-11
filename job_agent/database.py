"""SQLite state and append-only history."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .models import Profile, Status
from .migrations import migrate


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


SCHEMA = f"""
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY, identity_key TEXT NOT NULL UNIQUE,
    company TEXT NOT NULL, title TEXT NOT NULL, location TEXT NOT NULL,
    work_mode TEXT NOT NULL, description TEXT NOT NULL, skills TEXT NOT NULL,
    application_url TEXT, min_experience REAL, max_experience REAL,
    is_sample INTEGER NOT NULL CHECK(is_sample IN (0,1)),
    match_score INTEGER NOT NULL CHECK(match_score BETWEEN 0 AND 100),
    match_detail TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ({','.join(repr(s.value) for s in Status)})),
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS jobs_url ON jobs(application_url) WHERE application_url IS NOT NULL;
CREATE TABLE IF NOT EXISTS source_references (
    id INTEGER PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id),
    source TEXT NOT NULL, source_key TEXT NOT NULL, source_job_id TEXT,
    application_url TEXT, content_hash TEXT NOT NULL, imported_at TEXT NOT NULL,
    UNIQUE(source, source_key)
);
CREATE TABLE IF NOT EXISTS candidate_profile (
    id INTEGER PRIMARY KEY CHECK(id=1), config TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS status_history (
    id INTEGER PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id),
    previous_status TEXT, status TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY, action TEXT NOT NULL, job_id TEXT REFERENCES jobs(id),
    details TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_events BEGIN SELECT RAISE(ABORT, 'append_only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_events BEGIN SELECT RAISE(ABORT, 'append_only'); END;
CREATE TRIGGER IF NOT EXISTS history_no_update BEFORE UPDATE ON status_history BEGIN SELECT RAISE(ABORT, 'append_only'); END;
CREATE TRIGGER IF NOT EXISTS history_no_delete BEFORE DELETE ON status_history BEGIN SELECT RAISE(ABORT, 'append_only'); END;
"""


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as conn:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='jobs'").fetchone():
                conn.executescript(SCHEMA)
                conn.execute("PRAGMA user_version=1")
            conn.execute("INSERT OR IGNORE INTO candidate_profile VALUES (1, ?, ?)", (Profile().model_dump_json(), now()))
        with self.transaction() as conn:
            migrate(conn, self.path)

    @contextmanager
    def transaction(self):
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @staticmethod
    def audit(conn, action: str, details: dict, job_id: str | None = None):
        conn.execute("INSERT INTO audit_events(action, job_id, details, created_at) VALUES (?, ?, ?, ?)", (action, job_id, json.dumps(details), now()))

    def record_error(self, code: str):
        with self.transaction() as conn:
            self.audit(conn, "ERROR", {"code": code})

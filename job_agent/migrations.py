"""Atomic schema upgrades; use SQLite backup before touching existing v1 state."""
import sqlite3
from pathlib import Path


JOB_COLUMNS = {
    "category": "TEXT NOT NULL DEFAULT 'OTHER'",
    "priority": "TEXT NOT NULL DEFAULT 'P3'",
    "first_seen": "TEXT", "last_seen": "TEXT", "last_changed": "TEXT",
    "listing_url": "TEXT", "discovery_detail": "TEXT",
}
REF_COLUMNS = {"first_seen": "TEXT", "last_seen": "TEXT", "last_changed": "TEXT", "raw_hash": "TEXT", "listing_url": "TEXT", "snapshot": "TEXT"}
STATEMENTS = [
    """CREATE TABLE sources (
        id TEXT PRIMARY KEY, provider TEXT NOT NULL CHECK(provider IN ('greenhouse','lever')),
        company TEXT NOT NULL, board TEXT NOT NULL, region TEXT NOT NULL,
        enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
        last_success TEXT, last_attempt TEXT, last_error TEXT, health TEXT NOT NULL DEFAULT 'UNSCANNED',
        checkpoint TEXT NOT NULL DEFAULT '{}', next_scan_after TEXT,
        UNIQUE(provider, board, region))""",
    """CREATE TABLE discovery_runs (
        id TEXT PRIMARY KEY, status TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT,
        duration_seconds REAL, metrics TEXT NOT NULL, error TEXT)""",
    """CREATE TABLE discovery_source_runs (
        run_id TEXT NOT NULL REFERENCES discovery_runs(id), source_id TEXT NOT NULL REFERENCES sources(id),
        status TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT, duration_seconds REAL,
        metrics TEXT NOT NULL, error TEXT, PRIMARY KEY(run_id, source_id))""",
    """CREATE TABLE discovery_lease (
        id INTEGER PRIMARY KEY CHECK(id=1), run_id TEXT NOT NULL REFERENCES discovery_runs(id), expires_at TEXT NOT NULL)""",
    "CREATE INDEX source_job_ref ON source_references(source, source_key)",
    "CREATE TABLE search_background (id INTEGER PRIMARY KEY CHECK(id=1), config TEXT NOT NULL)",
]


def migrate(conn: sqlite3.Connection, path: Path):
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version == 5:
        return
    if version == 4:
        migrate_v5(conn, path)
        return
    if version not in (1, 2, 3):
        raise RuntimeError("unsupported_database_version")
    # Stable backup is created once, before the migration transaction; never overwritten.
    backup = path.with_suffix(path.suffix + (".pre-v2.bak" if version == 1 else ".pre-v3.bak" if version == 2 else ".pre-v4.bak"))
    if not backup.exists():
        with sqlite3.connect(backup) as target:
            conn.backup(target)
    conn.commit()
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute("BEGIN IMMEDIATE")
    try:
        if version == 1:
            for name, definition in JOB_COLUMNS.items(): conn.execute(f"ALTER TABLE jobs ADD COLUMN {name} {definition}")
            for name, definition in REF_COLUMNS.items(): conn.execute(f"ALTER TABLE source_references ADD COLUMN {name} {definition}")
            conn.execute("UPDATE jobs SET first_seen=created_at, last_seen=created_at, last_changed=updated_at")
            conn.execute("UPDATE source_references SET first_seen=imported_at, last_seen=imported_at, last_changed=imported_at, listing_url=application_url")
            for statement in STATEMENTS: conn.execute(statement)
            from .candidate import SearchBackground
            conn.execute("INSERT INTO search_background VALUES (1, ?)", (SearchBackground().model_dump_json(),))
        job_v3 = {
            "eligibility_state": "TEXT NOT NULL DEFAULT 'UNKNOWN'", "eligibility_explanation": "TEXT",
            "eligibility_evidence": "TEXT", "eligibility_confidence": "TEXT NOT NULL DEFAULT 'LOW'",
            "eligibility_evaluated_at": "TEXT", "seniority_level": "TEXT NOT NULL DEFAULT 'UNKNOWN'",
            "activity_status": "TEXT NOT NULL DEFAULT 'UNKNOWN'", "last_verified": "TEXT", "missing_scans": "INTEGER NOT NULL DEFAULT 0",
            "duplicate_group": "TEXT", "canonical_application_url": "TEXT", "content_hash": "TEXT"
        }
        source_v3 = {
            "career_url": "TEXT", "verified": "INTEGER NOT NULL DEFAULT 0", "verified_at": "TEXT",
            "verification_evidence": "TEXT", "india_relevant": "INTEGER", "source_cooldown_seconds": "INTEGER"
        }
        existing_jobs={row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
        existing_sources={row[1] for row in conn.execute("PRAGMA table_info(sources)")}
        for name, definition in job_v3.items():
            if name not in existing_jobs: conn.execute(f"ALTER TABLE jobs ADD COLUMN {name} {definition}")
        for name, definition in source_v3.items():
            if name not in existing_sources: conn.execute(f"ALTER TABLE sources ADD COLUMN {name} {definition}")
        conn.execute("UPDATE jobs SET activity_status=CASE WHEN discovery_detail IS NULL THEN 'UNKNOWN' ELSE 'ACTIVE' END, last_verified=last_seen, canonical_application_url=COALESCE(listing_url,application_url), duplicate_group=identity_key")
        job_v4={
            "published_at":"TEXT", "source_updated_at":"TEXT", "timestamp_provenance":"TEXT",
            "timestamp_confidence":"TEXT NOT NULL DEFAULT 'UNKNOWN'", "discovery_priority":"REAL NOT NULL DEFAULT 0",
            "location_bucket":"TEXT NOT NULL DEFAULT 'UNKNOWN'", "required_skills":"TEXT NOT NULL DEFAULT '[]'",
            "preferred_skills":"TEXT NOT NULL DEFAULT '[]'", "salary_min":"REAL", "salary_max":"REAL",
            "salary_currency":"TEXT", "salary_period":"TEXT", "required_experience_min":"REAL", "required_experience_max":"REAL", "experience_scope":"TEXT"
        }
        source_v4={"platform":"TEXT", "integration_state":"TEXT NOT NULL DEFAULT 'PUBLIC_FEED'"}
        for name,definition in job_v4.items(): conn.execute(f"ALTER TABLE jobs ADD COLUMN {name} {definition}")
        for name,definition in source_v4.items(): conn.execute(f"ALTER TABLE sources ADD COLUMN {name} {definition}")
        conn.execute("UPDATE sources SET platform=provider")
        conn.execute("""CREATE TABLE sources_v4 (
            id TEXT PRIMARY KEY, provider TEXT NOT NULL CHECK(provider IN ('greenhouse','lever','remoteok','wwr')),
            company TEXT NOT NULL, board TEXT NOT NULL, region TEXT NOT NULL, enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
            last_success TEXT,last_attempt TEXT,last_error TEXT,health TEXT NOT NULL DEFAULT 'UNSCANNED',checkpoint TEXT NOT NULL DEFAULT '{}',next_scan_after TEXT,
            career_url TEXT,verified INTEGER NOT NULL DEFAULT 0,verified_at TEXT,verification_evidence TEXT,india_relevant INTEGER,source_cooldown_seconds INTEGER,
            platform TEXT,integration_state TEXT NOT NULL DEFAULT 'PUBLIC_FEED',UNIQUE(provider,board,region))""")
        cols="id,provider,company,board,region,enabled,last_success,last_attempt,last_error,health,checkpoint,next_scan_after,career_url,verified,verified_at,verification_evidence,india_relevant,source_cooldown_seconds,platform,integration_state"
        conn.execute(f"INSERT INTO sources_v4({cols}) SELECT {cols} FROM sources")
        conn.execute("DROP TABLE sources")
        conn.execute("ALTER TABLE sources_v4 RENAME TO sources")
        conn.execute("CREATE INDEX jobs_filter_v4 ON jobs(activity_status, eligibility_state, category, match_score DESC, id)")
        conn.execute("CREATE INDEX jobs_published_v4 ON jobs(published_at DESC, id)")
        conn.execute("CREATE INDEX jobs_location_v4 ON jobs(location_bucket, id)")
        conn.execute("CREATE INDEX jobs_priority_v4 ON jobs(eligibility_state, discovery_priority DESC, id)")
        conn.execute("""CREATE TABLE source_platforms(name TEXT PRIMARY KEY, official_url TEXT NOT NULL, integration_state TEXT NOT NULL,
            operating_status TEXT NOT NULL, public_access TEXT, authentication TEXT, india_relevance TEXT,
            timestamps TEXT, verified_at TEXT NOT NULL, evidence TEXT NOT NULL)""")
        conn.execute("PRAGMA user_version=4")
        conn.commit()
        conn.execute("PRAGMA foreign_keys=ON")
        migrate_v5(conn, path)
    except Exception:
        conn.rollback()
        conn.execute("PRAGMA foreign_keys=ON")
        raise


def migrate_v5(conn: sqlite3.Connection, path: Path):
    """Add M2B state without rewriting jobs or manual tracking history."""
    backup = path.with_suffix(path.suffix + ".pre-v5.bak")
    if not backup.exists():
        with sqlite3.connect(backup) as target:
            conn.backup(target)
    conn.commit()
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.executescript("""
        CREATE TABLE candidate_profiles_v2 (
            id INTEGER PRIMARY KEY CHECK(id=1), version INTEGER NOT NULL,
            config TEXT NOT NULL, updated_at TEXT NOT NULL,
            resume_name TEXT, resume_hash TEXT, resume_reviewed INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE embedding_cache (
            content_hash TEXT NOT NULL, model_id TEXT NOT NULL, model_version TEXT NOT NULL,
            strategy TEXT NOT NULL, vector TEXT NOT NULL, created_at TEXT NOT NULL,
            PRIMARY KEY(content_hash, model_id, model_version, strategy)
        );
        CREATE TABLE job_recommendations (
            job_id TEXT PRIMARY KEY REFERENCES jobs(id), profile_version INTEGER NOT NULL,
            content_hash TEXT NOT NULL, score REAL NOT NULL, confidence TEXT NOT NULL,
            gate_state TEXT NOT NULL, semantic_score REAL, strategy TEXT NOT NULL,
            breakdown TEXT NOT NULL, explanation TEXT NOT NULL, ai_state TEXT NOT NULL,
            model_provenance TEXT, updated_at TEXT NOT NULL
        );
        CREATE TABLE llm_analysis_cache (
            cache_key TEXT PRIMARY KEY, provider TEXT NOT NULL, model TEXT NOT NULL,
            response TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE recommendation_runs (
            id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT NOT NULL,
            metrics TEXT NOT NULL
        );
        CREATE INDEX recommendations_rank_v5 ON job_recommendations(gate_state, score DESC, job_id);
        """)
        conn.execute("PRAGMA user_version=5")
        conn.commit()
    except Exception:
        conn.rollback()
        raise

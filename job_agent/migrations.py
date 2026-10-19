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
    if version == 17:
        return
    if version == 16:
        migrate_v17(conn,path)
        return
    if version == 15:
        migrate_v16(conn,path)
        migrate_v17(conn,path)
        return
    if version == 14:
        migrate_v15(conn,path)
        return
    if version == 13:
        migrate_v14(conn,path)
        return
    if version == 12:
        migrate_v13(conn,path)
        return
    if version == 11:
        migrate_v12(conn,path)
        return
    if version == 10:
        migrate_v11(conn,path)
        return
    if version == 9:
        migrate_v10(conn,path)
        return
    if version == 8:
        migrate_v9(conn,path)
        return
    if version == 7:
        migrate_v8(conn,path)
        return
    if version == 6:
        migrate_v7(conn, path)
        return
    if version == 5:
        migrate_v6(conn, path)
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
        migrate_v6(conn, path)
    except Exception:
        conn.rollback()
        raise

def migrate_v6(conn: sqlite3.Connection, path: Path):
    backup=path.with_suffix(path.suffix+".pre-v6.bak")
    if not backup.exists():
        with sqlite3.connect(backup) as target: conn.backup(target)
    conn.commit();conn.execute("BEGIN IMMEDIATE")
    try:
        conn.executescript("""
        CREATE TABLE resume_extractions(id TEXT PRIMARY KEY,resume_hash TEXT NOT NULL,format TEXT NOT NULL,extractor_version TEXT NOT NULL,created_at TEXT NOT NULL,page_count INTEGER NOT NULL,text_path TEXT NOT NULL);
        CREATE TABLE candidate_fact_proposals(id TEXT PRIMARY KEY,extraction_id TEXT NOT NULL REFERENCES resume_extractions(id),category TEXT NOT NULL,value TEXT NOT NULL,source_ref TEXT NOT NULL,confidence TEXT NOT NULL,status TEXT NOT NULL CHECK(status IN ('PENDING','ACCEPTED','REJECTED')),reviewed_value TEXT,created_at TEXT NOT NULL,reviewed_at TEXT);
        CREATE TABLE candidate_fact_audit(id INTEGER PRIMARY KEY,proposal_id TEXT NOT NULL,action TEXT NOT NULL,details TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TRIGGER fact_audit_no_update BEFORE UPDATE ON candidate_fact_audit BEGIN SELECT RAISE(ABORT,'append_only'); END;
        CREATE TRIGGER fact_audit_no_delete BEFORE DELETE ON candidate_fact_audit BEGIN SELECT RAISE(ABORT,'append_only'); END;
        """);conn.execute("PRAGMA user_version=6");conn.commit();migrate_v7(conn,path)
    except Exception:conn.rollback();raise

def migrate_v7(conn: sqlite3.Connection,path:Path):
    """Add M2D operational queues, evidence, coverage and immutable handoffs."""
    backup=path.with_suffix(path.suffix+".pre-v7.bak")
    if not backup.exists():
        with sqlite3.connect(backup) as target:conn.backup(target)
    conn.commit();conn.execute("BEGIN IMMEDIATE")
    try:
        conn.executescript("""
        CREATE TABLE m2d_sources(
          source_id TEXT PRIMARY KEY,display_name TEXT NOT NULL,stream TEXT NOT NULL,owner TEXT NOT NULL,
          official_url TEXT,implementation_state TEXT NOT NULL,connector TEXT,reference_time_ist TEXT,
          coverage_status TEXT NOT NULL DEFAULT 'UNATTEMPTED',bounded_scope TEXT NOT NULL DEFAULT '{}',
          queries TEXT NOT NULL DEFAULT '[]',filters TEXT NOT NULL DEFAULT '{}',pagination_strategy TEXT,
          cursor TEXT NOT NULL DEFAULT '{}',last_attempt TEXT,meaningful_success TEXT,next_due TEXT,
          blocker TEXT,attempts INTEGER NOT NULL DEFAULT 0,backlog INTEGER NOT NULL DEFAULT 0,updated_at TEXT NOT NULL);
        CREATE TABLE employer_registry(
          employer_key TEXT PRIMARY KEY,name TEXT NOT NULL UNIQUE,careers_url TEXT,headcount INTEGER,
          headcount_state TEXT NOT NULL DEFAULT 'UNKNOWN',evidence_url TEXT,verified_at TEXT,updated_at TEXT NOT NULL);
        CREATE TABLE m2d_tasks(
          task_id TEXT PRIMARY KEY,kind TEXT NOT NULL CHECK(kind IN ('DISCOVERY','VERIFICATION')),
          source_id TEXT REFERENCES m2d_sources(source_id),job_key TEXT,stream TEXT NOT NULL,category TEXT NOT NULL,
          payload TEXT NOT NULL DEFAULT '{}',status TEXT NOT NULL DEFAULT 'PENDING',priority INTEGER NOT NULL DEFAULT 0,
          due_at TEXT NOT NULL,lease_until TEXT,attempts INTEGER NOT NULL DEFAULT 0,max_attempts INTEGER NOT NULL DEFAULT 2,
          checkpoint TEXT NOT NULL DEFAULT '{}',blocker TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
        CREATE INDEX m2d_tasks_due_v7 ON m2d_tasks(status,due_at,priority DESC,stream,task_id);
        CREATE TABLE job_observations(
          observation_id TEXT PRIMARY KEY,job_key TEXT NOT NULL,stream TEXT NOT NULL,source_id TEXT NOT NULL,
          provider_id TEXT,canonical_url TEXT,observed_at TEXT NOT NULL,email_received_at TEXT,
          evidence TEXT NOT NULL DEFAULT '{}',snapshot_id TEXT,
          UNIQUE(source_id,provider_id,canonical_url));
        CREATE INDEX job_observations_key_v7 ON job_observations(job_key,stream,source_id);
        CREATE TABLE job_operational_state(
          job_key TEXT PRIMARY KEY,job_id TEXT REFERENCES jobs(id),lifecycle TEXT NOT NULL DEFAULT 'UNKNOWN',
          eligibility TEXT NOT NULL DEFAULT 'UNKNOWN',verification TEXT NOT NULL DEFAULT 'UNVERIFIED',
          readiness TEXT NOT NULL DEFAULT 'PROMISING_NEEDS_VERIFICATION',headcount_state TEXT NOT NULL DEFAULT 'UNKNOWN',
          payroll_state TEXT NOT NULL DEFAULT 'UNKNOWN',india_state TEXT NOT NULL DEFAULT 'UNKNOWN',
          active_state TEXT NOT NULL DEFAULT 'UNKNOWN',recipient_state TEXT NOT NULL DEFAULT 'UNKNOWN',
          missing_facts TEXT NOT NULL DEFAULT '[]',exclusion_reason TEXT,updated_at TEXT NOT NULL);
        CREATE TABLE job_evidence(
          evidence_id TEXT PRIMARY KEY,job_key TEXT NOT NULL,kind TEXT NOT NULL,state TEXT NOT NULL,
          factual TEXT, inference TEXT,evidence_url TEXT,observed_at TEXT NOT NULL,verified_at TEXT,checksum TEXT NOT NULL);
        CREATE INDEX job_evidence_key_v7 ON job_evidence(job_key,kind,verified_at);
        CREATE TABLE m2d_snapshots(
          snapshot_id TEXT PRIMARY KEY,run_id TEXT NOT NULL,stream TEXT NOT NULL,schema_version TEXT NOT NULL,
          completion_status TEXT NOT NULL,started_at TEXT NOT NULL,finished_at TEXT NOT NULL,
          distinct_jobs INTEGER NOT NULL,observations INTEGER NOT NULL,counts TEXT NOT NULL,
          artifact_name TEXT,artifact_checksum TEXT,created_at TEXT NOT NULL);
        CREATE TRIGGER m2d_snapshot_no_update BEFORE UPDATE ON m2d_snapshots BEGIN SELECT RAISE(ABORT,'immutable_snapshot'); END;
        CREATE TRIGGER m2d_snapshot_no_delete BEFORE DELETE ON m2d_snapshots BEGIN SELECT RAISE(ABORT,'immutable_snapshot'); END;
        CREATE TABLE m2d_consumer_checkpoints(
          consumer TEXT PRIMARY KEY,snapshot_id TEXT NOT NULL REFERENCES m2d_snapshots(snapshot_id),updated_at TEXT NOT NULL);
        CREATE TABLE m2d_imports(
          import_id TEXT PRIMARY KEY,report_identity TEXT NOT NULL,checksum TEXT NOT NULL UNIQUE,stream TEXT NOT NULL,
          imported_status_claim TEXT,rows_total INTEGER NOT NULL,rows_imported INTEGER NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE gmail_intake(
          message_id TEXT PRIMARY KEY,thread_id TEXT,received_at TEXT NOT NULL,labels TEXT NOT NULL,
          classification TEXT NOT NULL,vacancy_count INTEGER NOT NULL,import_id TEXT NOT NULL,
          cursor_value TEXT,classified_at TEXT NOT NULL);
        """)
        conn.execute("PRAGMA user_version=7");conn.commit();migrate_v8(conn,path)
    except Exception:conn.rollback();raise

def migrate_v8(conn:sqlite3.Connection,path:Path):
    """Allow separate requisitions to share natural title/company identity."""
    backup=path.with_suffix(path.suffix+".pre-v8.bak")
    if not backup.exists():
        with sqlite3.connect(backup) as target:conn.backup(target)
    create_sql=conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='jobs'").fetchone()[0]
    if "identity_key TEXT NOT NULL UNIQUE" not in create_sql:raise RuntimeError("unexpected_jobs_schema")
    indexes=[row[0] for row in conn.execute("SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='jobs' AND sql IS NOT NULL")]
    columns=[row[1] for row in conn.execute("PRAGMA table_info(jobs)")];names=",".join(columns)
    conn.commit();conn.execute("PRAGMA foreign_keys=OFF");conn.execute("BEGIN IMMEDIATE")
    try:
        rebuilt=create_sql.replace("CREATE TABLE jobs","CREATE TABLE jobs_v8",1).replace("identity_key TEXT NOT NULL UNIQUE","identity_key TEXT NOT NULL",1)
        conn.execute(rebuilt);conn.execute(f"INSERT INTO jobs_v8({names}) SELECT {names} FROM jobs");conn.execute("DROP TABLE jobs");conn.execute("ALTER TABLE jobs_v8 RENAME TO jobs")
        for statement in indexes:conn.execute(statement)
        conn.execute("PRAGMA user_version=8");conn.commit();conn.execute("PRAGMA foreign_keys=ON");migrate_v9(conn,path)
        if conn.execute("PRAGMA foreign_key_check").fetchone():raise RuntimeError("foreign_key_check_failed")
    except Exception:
        conn.rollback();conn.execute("PRAGMA foreign_keys=ON");raise

def migrate_v9(conn:sqlite3.Connection,path:Path):
    """Add durable M3 packets, evidence, revisions and draft-operation journal."""
    backup=path.with_suffix(path.suffix+".pre-v9.bak")
    if not backup.exists():
        with sqlite3.connect(backup) as target:conn.backup(target)
    conn.commit();conn.execute("BEGIN IMMEDIATE")
    try:
        conn.executescript("""
        CREATE TABLE application_packets(
          packet_id TEXT PRIMARY KEY,job_key TEXT NOT NULL UNIQUE,job_id TEXT REFERENCES jobs(id),
          status TEXT NOT NULL CHECK(status IN ('TEXT_PREPARED','NEEDS_USER_INFORMATION','CONTACT_VERIFICATION_PENDING','REVIEW_DRAFT_READY','GMAIL_DRAFT_PENDING','GMAIL_DRAFT_SAVED','GMAIL_DRAFT_UNCERTAIN','BLOCKED_INCOMPATIBLE')),
          current_version INTEGER NOT NULL DEFAULT 1,profile_version INTEGER NOT NULL,vacancy_version TEXT NOT NULL,
          document_versions TEXT NOT NULL DEFAULT '{}',missing_information TEXT NOT NULL DEFAULT '[]',
          required_documents TEXT NOT NULL DEFAULT '[]',manual_next_action TEXT NOT NULL,content_hash TEXT NOT NULL,
          created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
        CREATE INDEX application_packets_status_v9 ON application_packets(status,updated_at,packet_id);
        CREATE TABLE application_packet_versions(
          packet_id TEXT NOT NULL REFERENCES application_packets(packet_id),version INTEGER NOT NULL,
          subject TEXT NOT NULL,email_html TEXT NOT NULL,email_text TEXT NOT NULL,supporting_statement TEXT NOT NULL,
          fit_summary TEXT NOT NULL,gaps TEXT NOT NULL,provenance TEXT NOT NULL,generator TEXT NOT NULL,
          user_edited INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL,PRIMARY KEY(packet_id,version));
        CREATE TRIGGER packet_version_no_update BEFORE UPDATE ON application_packet_versions BEGIN SELECT RAISE(ABORT,'immutable_packet_version'); END;
        CREATE TRIGGER packet_version_no_delete BEFORE DELETE ON application_packet_versions BEGIN SELECT RAISE(ABORT,'immutable_packet_version'); END;
        CREATE TABLE application_questions(
          question_id TEXT PRIMARY KEY,packet_id TEXT NOT NULL REFERENCES application_packets(packet_id),
          question TEXT NOT NULL,source TEXT NOT NULL,source_ref TEXT NOT NULL,character_limit INTEGER,
          field_kind TEXT NOT NULL DEFAULT 'TEXT',created_at TEXT NOT NULL,UNIQUE(packet_id,source_ref));
        CREATE TABLE application_answers(
          answer_id TEXT PRIMARY KEY,question_id TEXT NOT NULL REFERENCES application_questions(question_id),
          version INTEGER NOT NULL,answer TEXT,status TEXT NOT NULL CHECK(status IN ('PROPOSED','NEEDS_USER_INFORMATION','USER_EDITED','APPROVED')),
          provenance TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(question_id,version));
        CREATE TABLE contact_evidence(
          contact_id TEXT PRIMARY KEY,job_key TEXT NOT NULL,name TEXT NOT NULL,employer TEXT NOT NULL,email TEXT,
          source_url TEXT,source_message_id TEXT,role_relevance TEXT NOT NULL,verification_status TEXT NOT NULL CHECK(verification_status IN ('VERIFIED','UNVERIFIED','NO_REPLY')),
          verified_at TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
        CREATE INDEX contact_job_v9 ON contact_evidence(job_key,verification_status,updated_at);
        CREATE TABLE gmail_draft_operations(
          operation_id TEXT PRIMARY KEY,job_key TEXT NOT NULL,contact_id TEXT NOT NULL REFERENCES contact_evidence(contact_id),
          intent TEXT NOT NULL,received_message_id TEXT NOT NULL DEFAULT '',packet_id TEXT NOT NULL REFERENCES application_packets(packet_id),
          packet_version INTEGER NOT NULL,state TEXT NOT NULL CHECK(state IN ('PENDING','SAVED','UNCERTAIN','RESOLVED_NO_DRAFT')),
          gmail_draft_id TEXT,gmail_message_id TEXT,error_code TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
          UNIQUE(job_key,contact_id,intent,received_message_id));
        """)
        conn.execute("PRAGMA user_version=9");conn.commit();migrate_v10(conn,path)
    except Exception:conn.rollback();raise

def migrate_v10(conn:sqlite3.Connection,path:Path):
    """Add immutable effective-profile revisions and non-destructive proposal links."""
    backup=path.with_suffix(path.suffix+".pre-v10.bak")
    if not backup.exists():
        with sqlite3.connect(backup) as target:conn.backup(target)
    conn.commit();conn.execute("BEGIN IMMEDIATE")
    try:
        conn.executescript("""
        CREATE TABLE candidate_profile_revisions(
          revision_id TEXT PRIMARY KEY,profile_version INTEGER NOT NULL,reason TEXT NOT NULL,
          before_hash TEXT NOT NULL,after_hash TEXT NOT NULL,changes TEXT NOT NULL,
          provenance TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TRIGGER profile_revision_no_update BEFORE UPDATE ON candidate_profile_revisions BEGIN SELECT RAISE(ABORT,'immutable_profile_revision'); END;
        CREATE TRIGGER profile_revision_no_delete BEFORE DELETE ON candidate_profile_revisions BEGIN SELECT RAISE(ABORT,'immutable_profile_revision'); END;
        CREATE TABLE candidate_fact_links(
          proposal_id TEXT PRIMARY KEY REFERENCES candidate_fact_proposals(id),link_state TEXT NOT NULL,
          confirmed_fact_key TEXT NOT NULL,provenance TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TRIGGER fact_link_no_update BEFORE UPDATE ON candidate_fact_links BEGIN SELECT RAISE(ABORT,'immutable_fact_link'); END;
        CREATE TRIGGER fact_link_no_delete BEFORE DELETE ON candidate_fact_links BEGIN SELECT RAISE(ABORT,'immutable_fact_link'); END;
        """)
        conn.execute("PRAGMA user_version=10");conn.commit();migrate_v11(conn,path)
    except Exception:conn.rollback();raise

def migrate_v11(conn:sqlite3.Connection,path:Path):
    """Add resumable live Gmail intervals and ordinary workflow run journals."""
    backup=path.with_suffix(path.suffix+".pre-v11.bak")
    if not backup.exists():
        with sqlite3.connect(backup) as target:conn.backup(target)
    conn.commit();conn.execute("BEGIN IMMEDIATE")
    try:
        conn.executescript("""
        CREATE TABLE gmail_live_runs(
          run_id TEXT PRIMARY KEY,interval_start TEXT NOT NULL,interval_end TEXT NOT NULL,
          status TEXT NOT NULL CHECK(status IN ('RUNNING','PARTIAL','COMPLETED','FAILED')),
          next_page_token TEXT,pages INTEGER NOT NULL DEFAULT 0,messages_seen INTEGER NOT NULL DEFAULT 0,
          messages_classified INTEGER NOT NULL DEFAULT 0,vacancies INTEGER NOT NULL DEFAULT 0,
          error_code TEXT,started_at TEXT NOT NULL,updated_at TEXT NOT NULL,completed_at TEXT,
          UNIQUE(interval_start,interval_end));
        CREATE TABLE workflow_runs(
          run_id TEXT PRIMARY KEY,status TEXT NOT NULL CHECK(status IN ('RUNNING','PARTIAL','COMPLETED','FAILED')),
          started_at TEXT NOT NULL,finished_at TEXT,stage_results TEXT NOT NULL DEFAULT '{}',
          resume_command TEXT NOT NULL,error_count INTEGER NOT NULL DEFAULT 0);
        """)
        conn.execute("PRAGMA user_version=11");conn.commit()
        migrate_v12(conn,path)
    except Exception:conn.rollback();raise


def migrate_v12(conn:sqlite3.Connection,path:Path):
    """Extend the provider constraint without changing source IDs or child references."""
    backup=path.with_suffix(path.suffix+".pre-v12.bak")
    if not backup.exists():
        with sqlite3.connect(backup) as target:conn.backup(target)
    create_sql=conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='sources'").fetchone()[0]
    columns=','.join(row[1] for row in conn.execute("PRAGMA table_info(sources)"))
    conn.commit();conn.execute("PRAGMA foreign_keys=OFF");conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(create_sql.replace('CREATE TABLE "sources"','CREATE TABLE sources_v12',1).replace('CREATE TABLE sources (','CREATE TABLE sources_v12 (',1).replace("'remoteok','wwr'","'remoteok','wwr','smartrecruiters'"))
        conn.execute(f"INSERT INTO sources_v12({columns}) SELECT {columns} FROM sources")
        conn.execute("DROP TABLE sources");conn.execute("ALTER TABLE sources_v12 RENAME TO sources")
        if conn.execute("PRAGMA foreign_key_check").fetchone():raise RuntimeError("foreign_key_check_failed")
        conn.execute("PRAGMA user_version=12");conn.commit()
    except Exception:conn.rollback();raise
    finally:conn.execute("PRAGMA foreign_keys=ON")
    migrate_v13(conn,path)


def migrate_v13(conn:sqlite3.Connection,path:Path):
    """Add Amazon public search provider, preserving source identities and journals."""
    backup=path.with_suffix(path.suffix+".pre-v13.bak")
    if not backup.exists():
        with sqlite3.connect(backup) as target:conn.backup(target)
    create_sql=conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='sources'").fetchone()[0]
    columns=','.join(row[1] for row in conn.execute("PRAGMA table_info(sources)"))
    conn.commit();conn.execute("PRAGMA foreign_keys=OFF");conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(create_sql.replace('CREATE TABLE "sources"','CREATE TABLE sources_v13',1).replace('CREATE TABLE sources (','CREATE TABLE sources_v13 (',1).replace("'smartrecruiters'","'smartrecruiters','amazon'"))
        conn.execute(f"INSERT INTO sources_v13({columns}) SELECT {columns} FROM sources")
        conn.execute("DROP TABLE sources");conn.execute("ALTER TABLE sources_v13 RENAME TO sources")
        if conn.execute("PRAGMA foreign_key_check").fetchone():raise RuntimeError("foreign_key_check_failed")
        conn.execute("PRAGMA user_version=13");conn.commit()
    except Exception:conn.rollback();raise
    finally:conn.execute("PRAGMA foreign_keys=ON")
    migrate_v14(conn,path)


def migrate_v14(conn:sqlite3.Connection,path:Path):
    """Allow genuinely unknown alert metadata in the canonical opportunity table."""
    backup=path.with_suffix(path.suffix+'.pre-v14.bak')
    if not backup.exists():
        with sqlite3.connect(backup) as target:conn.backup(target)
    ddl=conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='jobs'").fetchone()[0]
    indexes=[r[0] for r in conn.execute("SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='jobs' AND sql IS NOT NULL")]
    columns=','.join(r[1] for r in conn.execute('pragma table_info(jobs)'))
    conn.commit();conn.execute('PRAGMA foreign_keys=OFF');conn.execute('BEGIN IMMEDIATE')
    try:
        ddl=ddl.replace('CREATE TABLE "jobs"','CREATE TABLE jobs_v14',1).replace('CREATE TABLE jobs (','CREATE TABLE jobs_v14 (',1)
        for field in ('company','title','location'):ddl=ddl.replace(field+' TEXT NOT NULL',field+' TEXT')
        conn.execute(ddl);conn.execute(f'INSERT INTO jobs_v14({columns}) SELECT {columns} FROM jobs');conn.execute('DROP TABLE jobs');conn.execute('ALTER TABLE jobs_v14 RENAME TO jobs')
        for sql in indexes:conn.execute(sql)
        conn.execute('CREATE TABLE email_extractions(message_id TEXT NOT NULL,parser_version TEXT NOT NULL,family TEXT NOT NULL,classification TEXT NOT NULL,report TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(message_id,parser_version))')
        conn.execute('CREATE TABLE alert_url_resolutions(url_hash TEXT PRIMARY KEY,result_url TEXT,state TEXT NOT NULL,error_code TEXT,checked_at TEXT NOT NULL,next_retry_after TEXT)')
        if conn.execute('PRAGMA foreign_key_check').fetchone():raise RuntimeError('foreign_key_check_failed')
        conn.execute('PRAGMA user_version=14');conn.commit()
    except Exception:conn.rollback();raise
    finally:conn.execute('PRAGMA foreign_keys=ON')
    migrate_v15(conn,path)


def migrate_v15(conn,path):
    """Add preparation journals without changing discovery/profile/application rows."""
    backup=path.with_suffix(path.suffix+'.pre-v15.bak')
    if not backup.exists():
        with sqlite3.connect(backup) as target:conn.backup(target)
    conn.executescript('''
      CREATE TABLE browser_batches(id TEXT PRIMARY KEY,status TEXT NOT NULL,created_at TEXT NOT NULL,finished_at TEXT,error_code TEXT);
      CREATE TABLE browser_applications(id TEXT PRIMARY KEY,batch_id TEXT NOT NULL REFERENCES browser_batches(id),
        job_id TEXT NOT NULL REFERENCES jobs(id),identity TEXT NOT NULL UNIQUE,url TEXT NOT NULL,ats TEXT NOT NULL,
        state TEXT NOT NULL,target_id TEXT,session_id TEXT,inspection TEXT NOT NULL DEFAULT '{}',
        missing TEXT NOT NULL DEFAULT '[]',checks TEXT NOT NULL DEFAULT '[]',documents TEXT NOT NULL DEFAULT '[]',
        updated_at TEXT NOT NULL,confirmation_ref TEXT);
      CREATE TABLE browser_operations(id TEXT PRIMARY KEY,application_id TEXT NOT NULL REFERENCES browser_applications(id),
        kind TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,state TEXT NOT NULL,error_code TEXT,
        updated_at TEXT NOT NULL,next_action TEXT,UNIQUE(application_id,kind,id));
      CREATE TABLE browser_events(id INTEGER PRIMARY KEY,application_id TEXT REFERENCES browser_applications(id),
        event TEXT NOT NULL,details TEXT NOT NULL,created_at TEXT NOT NULL);
      CREATE TRIGGER browser_events_no_update BEFORE UPDATE ON browser_events BEGIN SELECT RAISE(ABORT,'append_only'); END;
      CREATE TRIGGER browser_events_no_delete BEFORE DELETE ON browser_events BEGIN SELECT RAISE(ABORT,'append_only'); END;
      PRAGMA user_version=15;
    ''')
    migrate_v16(conn,path)
    migrate_v17(conn,path)


def migrate_v16(conn,path):
    """Add independent outcomes and leased work; retain all original rows/history."""
    backup=path.with_suffix(path.suffix+'.pre-v16.bak')
    if not backup.exists():
        with sqlite3.connect(backup) as target:conn.backup(target)
    conn.executescript('''
      BEGIN IMMEDIATE;
      ALTER TABLE browser_applications ADD COLUMN application_outcome TEXT NOT NULL DEFAULT 'NOT_SUBMITTED';
      ALTER TABLE browser_applications ADD COLUMN session_health TEXT NOT NULL DEFAULT 'UNKNOWN';
      ALTER TABLE browser_applications ADD COLUMN preparation_state TEXT NOT NULL DEFAULT 'PREPARING';
      ALTER TABLE browser_applications ADD COLUMN last_sync_at TEXT;
      ALTER TABLE browser_applications ADD COLUMN completed_fields INTEGER NOT NULL DEFAULT 0;
      ALTER TABLE browser_applications ADD COLUMN phase TEXT NOT NULL DEFAULT 'Awaiting preparation';
      ALTER TABLE browser_applications ADD COLUMN retry_condition TEXT;
      CREATE TABLE browser_workflows(
        id TEXT PRIMARY KEY,kind TEXT NOT NULL,batch_id TEXT REFERENCES browser_batches(id),
        application_ids TEXT NOT NULL,state TEXT NOT NULL,owner TEXT,worker_pid INTEGER,
        heartbeat_at TEXT,lease_until TEXT,phase TEXT NOT NULL,cursor INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,updated_at TEXT NOT NULL,finished_at TEXT,error_code TEXT,retry_condition TEXT);
      CREATE INDEX browser_workflows_active ON browser_workflows(state,lease_until);
      CREATE TABLE browser_worker_events(id INTEGER PRIMARY KEY,workflow_id TEXT NOT NULL REFERENCES browser_workflows(id),event TEXT NOT NULL,details TEXT NOT NULL,created_at TEXT NOT NULL);
      CREATE TRIGGER browser_worker_events_no_update BEFORE UPDATE ON browser_worker_events BEGIN SELECT RAISE(ABORT,'append_only'); END;
      CREATE TRIGGER browser_worker_events_no_delete BEFORE DELETE ON browser_worker_events BEGIN SELECT RAISE(ABORT,'append_only'); END;
      UPDATE browser_applications SET preparation_state=CASE WHEN state IN ('SESSION_LOST','USER_REPORTED_SUBMITTED','SUBMISSION_CONFIRMED') THEN 'AWAITING_INSPECTION' ELSE state END,
        session_health=CASE WHEN state='SESSION_LOST' THEN 'LOST' WHEN target_id IS NOT NULL THEN 'CONNECTED' ELSE 'UNKNOWN' END;
      UPDATE browser_applications SET application_outcome='USER_REPORTED_SUBMITTED' WHERE state IN ('USER_REPORTED_SUBMITTED','SUBMISSION_CONFIRMED') OR EXISTS(
        SELECT 1 FROM browser_events e WHERE e.application_id=browser_applications.id AND json_extract(e.details,'$.state') IN ('USER_REPORTED_SUBMITTED','SUBMISSION_CONFIRMED'));
      UPDATE browser_applications SET application_outcome='SUBMISSION_CONFIRMED' WHERE confirmation_ref GLOB 'browser-confirmation:*' AND length(confirmation_ref)=85;
      UPDATE browser_applications SET state=application_outcome WHERE application_outcome<>'NOT_SUBMITTED';
      PRAGMA user_version=16;
      COMMIT;
    ''')


def migrate_v17(conn,path):
    """Append-only requirement snapshots; no historical evidence/profile rewrite."""
    backup=path.with_suffix(path.suffix+'.pre-v17.bak')
    if not backup.exists():
        with sqlite3.connect(backup) as target:conn.backup(target)
    conn.executescript("""
      BEGIN IMMEDIATE;
      CREATE TABLE requirement_assessments(id TEXT NOT NULL,job_id TEXT NOT NULL REFERENCES jobs(id),source_hash TEXT NOT NULL,extractor_version TEXT NOT NULL,profile_hash TEXT NOT NULL,state TEXT NOT NULL,report TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(id,job_id));
      CREATE INDEX requirement_assessments_job ON requirement_assessments(job_id,created_at);
      CREATE TRIGGER requirement_assessments_no_update BEFORE UPDATE ON requirement_assessments BEGIN SELECT RAISE(ABORT,'append_only'); END;
      CREATE TRIGGER requirement_assessments_no_delete BEFORE DELETE ON requirement_assessments BEGIN SELECT RAISE(ABORT,'append_only'); END;
      PRAGMA user_version=17;
      COMMIT;
    """)

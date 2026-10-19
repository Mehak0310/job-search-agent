"""Explicit configuration sync; normal server startup does not re-enable toggled sources."""
import json
import sqlite3
from pathlib import Path

from .candidate import SearchBackground
from .database import Database
from .discovery_models import DiscoveryConfig, SourceConfig


class Registry:
    def __init__(self, db: Database):
        self.db = db

    def sync(self, config: DiscoveryConfig):
        if len({s.id for s in config.sources}) != len(config.sources):
            raise ValueError("duplicate_source_id")
        with self.db.transaction() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT 1 FROM discovery_lease").fetchone():
                raise ValueError("discovery_in_progress")
            for source in config.sources:
                existing = conn.execute("SELECT * FROM sources WHERE id=?", (source.id,)).fetchone()
                if existing and any(existing[k] != getattr(source, k) for k in ("provider", "board", "region", "company")):
                    raise ValueError("source_identity_immutable")
                conn.execute("""INSERT INTO sources(id, provider, company, board, region, enabled, career_url, verified, verified_at, verification_evidence, india_relevant, source_cooldown_seconds, platform, integration_state) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PUBLIC_FEED')
                    ON CONFLICT(id) DO UPDATE SET enabled=excluded.enabled, career_url=excluded.career_url, verified=excluded.verified, verified_at=excluded.verified_at, verification_evidence=excluded.verification_evidence, india_relevant=excluded.india_relevant, source_cooldown_seconds=excluded.source_cooldown_seconds,platform=excluded.platform""", (source.id, source.provider, source.company, source.board, source.region, int(source.enabled), source.career_url, int(source.verified), source.verified_at, source.verification_evidence, None if source.india_relevant is None else int(source.india_relevant), source.cooldown_seconds,source.provider))
            from .platforms import records
            conn.executemany("INSERT OR REPLACE INTO source_platforms VALUES (?,?,?,?,?,?,?,?,?,?)",records())
            self.db.audit(conn, "SOURCES_CONFIGURED", {"count": len(config.sources)})

    def seed(self, config: DiscoveryConfig):
        with self.db.transaction() as conn:
            existing = {row[0] for row in conn.execute("SELECT id FROM sources")}
        missing = [source for source in config.sources if source.id not in existing]
        if missing:
            # Install new configured sources without resetting user toggles or cursors.
            self.sync(config.model_copy(update={"sources":missing}))

    def list(self) -> list[dict]:
        with self.db.transaction() as conn:
            sources = [dict(row) for row in conn.execute("SELECT * FROM sources ORDER BY id")]
            for source in sources:
                last = conn.execute("SELECT metrics FROM discovery_source_runs WHERE source_id=? ORDER BY started_at DESC,run_id DESC LIMIT 1", (source['id'],)).fetchone()
                source['last_run_metrics'] = json.loads(last['metrics']) if last else None
                source['retained_job_count'] = conn.execute("SELECT COUNT(DISTINCT job_id) FROM source_references WHERE source=?", (source['id'],)).fetchone()[0]
                source["enabled"] = bool(source["enabled"])
                source["verified"] = bool(source["verified"])
                source["india_relevant"] = None if source["india_relevant"] is None else bool(source["india_relevant"])
                source["checkpoint"] = json.loads(source["checkpoint"])
            return sources

    def toggle(self, source_id: str, enabled: bool) -> bool:
        with self.db.transaction() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if not conn.execute("SELECT 1 FROM sources WHERE id=?", (source_id,)).fetchone():
                return False
            conn.execute("UPDATE sources SET enabled=? WHERE id=?", (int(enabled), source_id))
            self.db.audit(conn, "SOURCE_TOGGLED", {"source_id": source_id, "enabled": enabled})
        return True

    def background(self) -> SearchBackground:
        with self.db.transaction() as conn:
            return SearchBackground.model_validate_json(conn.execute("SELECT config FROM search_background WHERE id=1").fetchone()[0])


def load_config(path: str | Path) -> DiscoveryConfig:
    content = Path(path).read_bytes()
    if len(content) > 65536:
        raise ValueError("config_too_large")
    return DiscoveryConfig.model_validate_json(content)

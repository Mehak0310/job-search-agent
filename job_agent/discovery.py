"""Deterministic, bounded, isolated discovery with a cross-process lease."""
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

import httpx

from .database import now
from .discovery_models import COUNTERS, DiscoverySettings, SourceConfig, metrics
from .discovery_store import persist_batch, reconcile_missing, touch_not_modified
from .public_connectors import CONNECTORS, ProviderError, PublicReader, RequestBudget
from .registry import Registry
from .service import JobService


class RunBusy(ValueError):
    pass


def future_timestamp(seconds: float) -> str:
    try:
        return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()
    except OverflowError:
        return datetime.max.replace(tzinfo=timezone.utc).isoformat()


class Discovery:
    def __init__(self, db, settings=None, client_factory=None):
        self.db = db
        self.settings = settings or DiscoverySettings()
        self.registry = Registry(db)
        self.client_factory = client_factory or (lambda: httpx.Client(trust_env=False, follow_redirects=False, headers={"Accept": "application/json", "User-Agent": "LocalJobAgent/0.2 public-board-discovery"}))
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="job-discovery")

    def claim(self) -> str:
        run_id = uuid.uuid4().hex
        with self.db.transaction() as conn:
            conn.execute("BEGIN IMMEDIATE")
            lease = conn.execute("SELECT * FROM discovery_lease").fetchone()
            if lease:
                if lease["expires_at"] > now():
                    raise RunBusy("discovery_in_progress")
                conn.execute("UPDATE discovery_runs SET status='INTERRUPTED', finished_at=?, error='lease_expired' WHERE id=? AND status='RUNNING'", (now(), lease["run_id"]))
                conn.execute("DELETE FROM discovery_lease")
                self.db.audit(conn, "DISCOVERY_INTERRUPTED", {"run_id": lease["run_id"]})
            conn.execute("INSERT INTO discovery_runs(id, status, started_at, metrics) VALUES (?, 'RUNNING', ?, ?)", (run_id, now(), json.dumps(metrics())))
            # Extra grace is longer than a request timeout; stale leases recover crashed workers.
            conn.execute("INSERT INTO discovery_lease VALUES (1, ?, ?)", (run_id, future_timestamp(self.settings.max_runtime_seconds + 60)))
            self.db.audit(conn, "DISCOVERY_STARTED", {"run_id": run_id})
        return run_id

    def start(self) -> str:
        run_id = self.claim()
        try:
            self.executor.submit(self.execute, run_id)
        except RuntimeError:
            self.finish(run_id, metrics(), 0, "FAILED", "worker_unavailable")
            raise
        return run_id

    def finish(self, run_id, totals, duration, status, error=None):
        with self.db.transaction() as conn:
            conn.execute("BEGIN IMMEDIATE")
            totals.update({
                "total_sources_configured": conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0],
                "verified_sources": conn.execute("SELECT COUNT(*) FROM sources WHERE verified=1").fetchone()[0],
                "enabled_sources": conn.execute("SELECT COUNT(*) FROM sources WHERE enabled=1").fetchone()[0],
                "healthy_sources": conn.execute("SELECT COUNT(*) FROM sources WHERE health IN ('SUCCESS','PARTIAL')").fetchone()[0],
                "india_eligible_jobs": conn.execute("SELECT COUNT(*) FROM jobs WHERE eligibility_state='ELIGIBLE' AND discovery_detail IS NOT NULL").fetchone()[0],
                "unknown_eligibility_jobs": conn.execute("SELECT COUNT(*) FROM jobs WHERE eligibility_state='UNKNOWN' AND discovery_detail IS NOT NULL").fetchone()[0],
            })
            for label,hours in (("1h",1),("6h",6),("12h",12),("24h",24),("48h",48)):
                totals["posted_"+label]=conn.execute("SELECT COUNT(*) FROM jobs WHERE published_at>=datetime('now',?)",(f"-{hours} hours",)).fetchone()[0]
            totals["unknown_posting_dates"]=conn.execute("SELECT COUNT(*) FROM jobs WHERE published_at IS NULL AND discovery_detail IS NOT NULL").fetchone()[0]
            totals["fresh_india_eligible_jobs"]=conn.execute("SELECT COUNT(*) FROM jobs WHERE published_at>=datetime('now','-48 hours') AND eligibility_state='ELIGIBLE'").fetchone()[0]
            totals["fresh_high_match_jobs"]=conn.execute("SELECT COUNT(*) FROM jobs WHERE published_at>=datetime('now','-48 hours') AND match_score>=70").fetchone()[0]
            lags=[r[0] for r in conn.execute("SELECT (julianday(first_seen)-julianday(published_at))*24 FROM jobs WHERE published_at IS NOT NULL AND first_seen>=published_at ORDER BY 1")]
            totals["median_discovery_lag_hours"]=round(lags[len(lags)//2],3) if lags else None
            relevant = totals["new_jobs"] + totals["updated_jobs"]
            totals["requests_per_new_relevant_job"] = round(totals["requests"] / relevant, 3) if relevant else None
            totals["runtime_per_new_relevant_job"] = round(duration / relevant, 3) if relevant else None
            conn.execute("UPDATE discovery_runs SET status=?, finished_at=?, duration_seconds=?, metrics=?, error=? WHERE id=?", (status, now(), round(duration, 3), json.dumps(totals), error, run_id))
            conn.execute("DELETE FROM discovery_lease WHERE run_id=?", (run_id,))
            self.db.audit(conn, "DISCOVERY_FINISHED", {"run_id": run_id, "status": status, **totals})

    def execute(self, run_id):
        started = time.monotonic()
        budget, totals, error = RequestBudget(self.settings), metrics(), None
        try:
            sources = [source for source in self.registry.list() if source["enabled"]]
            background = self.registry.background()
            profile = JobService(self.db)._profile
            with self.db.transaction() as conn:
                preferences = profile(conn)
            with self.client_factory() as client:
                prefetched = {}
                eligible = [s for s in sources if not s["next_scan_after"] or s["next_scan_after"] <= now()]
                def fetch(source):
                    local=metrics()
                    try:
                        connector=CONNECTORS[source["provider"]]()
                        data={name:source[name] for name in SourceConfig.model_fields if name in source}; data["cooldown_seconds"]=source.get("source_cooldown_seconds")
                        config=SourceConfig(**data)
                        return connector,config,connector.fetch(config,PublicReader(client,budget,local),source["checkpoint"]),local,None
                    except Exception as failure:
                        return None,None,None,local,failure
                with ThreadPoolExecutor(max_workers=self.settings.concurrency_limit,thread_name_prefix="source-fetch") as pool:
                    futures={pool.submit(fetch,s):s["id"] for s in eligible}
                    for future in as_completed(futures): prefetched[futures[future]]=future.result()
                for source in sources:
                    local, status, code, checkpoint = metrics(), "SUCCESS", None, source["checkpoint"]
                    source_started = time.monotonic()
                    source_started_at = now()
                    with self.db.transaction() as conn:
                        enabled = conn.execute("SELECT enabled FROM sources WHERE id=?", (source["id"],)).fetchone()[0]
                    if not enabled or source["next_scan_after"] and source["next_scan_after"] > now():
                        status = "SKIPPED"
                        local["skipped_sources"] = 1
                    else:
                        with self.db.transaction() as conn:
                            conn.execute("UPDATE sources SET last_attempt=? WHERE id=?", (source_started_at, source["id"]))
                        try:
                            connector,config,batch,fetched,failure=prefetched[source["id"]]
                            local.update(fetched)
                            if failure: raise failure
                            if batch.not_modified:
                                touch_not_modified(self.db, source["id"], local)
                            else:
                                persist_batch(self.db, config, connector, batch.records, background, preferences, local, budget)
                                reconcile_missing(self.db, source["id"], {str(r.get("id")) for r in batch.records if isinstance(r, dict) and r.get("id") is not None})
                            checkpoint = batch.checkpoint
                            status = "PARTIAL" if local["rejected_records"] else "SUCCESS"
                            cooldown = source.get("source_cooldown_seconds") if source.get("source_cooldown_seconds") is not None else self.settings.cooldown_seconds
                            cache_control = checkpoint.get("cache-control", "")
                            import re
                            age = re.search(r"(?:^|,)\s*max-age=(\d+)", cache_control)
                            if age:
                                cooldown = max(cooldown, min(int(age[1]), 86400))
                            with self.db.transaction() as conn:
                                conn.execute("UPDATE sources SET last_success=?, last_error=NULL, health=?, checkpoint=?, next_scan_after=? WHERE id=?", (now(), status, json.dumps(checkpoint), future_timestamp(cooldown), source["id"]))
                        except Exception as failure:
                            status, code = "FAILED", failure.code if isinstance(failure, ProviderError) else "source_internal_error"
                            local["failed_sources"] = 1
                            # Ensure rolled-back writes never inflate committed metrics.
                            for counter in ("new_jobs", "updated_jobs", "unchanged_jobs", "duplicates", "rejected_records"):
                                local[counter] = 0
                            with self.db.transaction() as conn:
                                conn.execute("UPDATE sources SET health='FAILED', last_error=?, next_scan_after=? WHERE id=?", (code, future_timestamp(max(self.settings.cooldown_seconds, getattr(failure, "retry_after", 0))), source["id"]))
                                self.db.audit(conn, "DISCOVERY_SOURCE_FAILED", {"source_id": source["id"], "code": code})
                    with self.db.transaction() as conn:
                        conn.execute("INSERT INTO discovery_source_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (run_id, source["id"], status, source_started_at, now(), round(time.monotonic() - source_started, 3), json.dumps(local), code))
                    for counter in COUNTERS:
                        totals[counter] += local[counter]
        except Exception:
            # Safe diagnostic only; never log external descriptions/headers/exception values.
            error = "discovery_internal_error"
        status = "FAILED" if error else "PARTIAL" if totals["failed_sources"] or totals["rejected_records"] else "COMPLETED"
        self.finish(run_id, totals, time.monotonic() - started, status, error)
        return self.get_run(run_id)

    def get_run(self, run_id):
        with self.db.transaction() as conn:
            row = conn.execute("SELECT * FROM discovery_runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                return None
            result = dict(row)
            result["metrics"] = json.loads(result["metrics"])
            result["sources"] = []
            for item in conn.execute("SELECT * FROM discovery_source_runs WHERE run_id=? ORDER BY source_id", (run_id,)):
                source = dict(item)
                source["metrics"] = json.loads(source["metrics"])
                result["sources"].append(source)
            return result

    def latest(self):
        with self.db.transaction() as conn:
            row = conn.execute("SELECT id FROM discovery_runs ORDER BY started_at DESC LIMIT 1").fetchone()
        return self.get_run(row[0]) if row else None

    def close(self):
        self.executor.shutdown(wait=True)

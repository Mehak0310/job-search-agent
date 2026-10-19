import json
import sqlite3
import threading
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from job_agent.candidate import SearchBackground
from job_agent.database import Database, SCHEMA
from job_agent.discovery import Discovery, RunBusy, future_timestamp
from job_agent.discovery_models import DiscoveryConfig, DiscoverySettings, SourceConfig
from job_agent.main import create_app
from job_agent.migrations import migrate
from job_agent.models import Profile, Status
from job_agent.registry import Registry, load_config
from job_agent.service import JobService


def config(**settings):
    return DiscoveryConfig(settings=DiscoverySettings(cooldown_seconds=0, retry_limit=0, **settings), sources=[SourceConfig(id="gh", provider="greenhouse", company="Acme", board="acme", enabled=True), SourceConfig(id="lever", provider="lever", company="Acme", board="acme", enabled=True)])


@pytest.fixture
def system(tmp_path, greenhouse_record, lever_record):
    state = {"gh": greenhouse_record, "lever": lever_record, "gh_status": 200, "lever_status": 200}
    def handler(request):
        gh = request.url.host == "boards-api.greenhouse.io"
        status = state["gh_status" if gh else "lever_status"]
        payload = {"jobs": [state["gh"]], "meta": {"total": 1}} if gh else [state["lever"]]
        return httpx.Response(status, json=payload)
    cfg = config()
    db = Database(tmp_path / "jobs.sqlite3")
    registry = Registry(db)
    registry.sync(cfg)
    discovery = Discovery(db, cfg.settings, lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    yield discovery, state
    discovery.close()


def run(discovery):
    return discovery.execute(discovery.claim())


def test_incremental_cross_source_updates_preserve_status(system):
    discovery, state = system
    first = run(discovery)
    assert first["status"] == "COMPLETED"
    assert first["metrics"]["new_jobs"] == 1 and first["metrics"]["duplicates"] == 1
    service = JobService(discovery.db)
    job = service.list_jobs()[0]
    job_id = job["id"]
    assert job["category"] == "FRONTEND_LEADERSHIP" and job["priority"] == "P1"
    assert len(service.get_job(job_id)["sources"]) == 2
    service.set_status(job_id, Status.SUBMITTED)
    unchanged = run(discovery)
    assert unchanged["metrics"]["unchanged_jobs"] == 2 and unchanged["metrics"]["new_jobs"] == 0
    assert len(service.list_jobs()) == 1
    assert service.get_job(job_id)["last_changed"] == job["last_changed"]
    state["gh"] = state["gh"] | {"content": state["gh"]["content"] + "<p>Python required.</p>"}
    updated = run(discovery)
    assert updated["metrics"]["updated_jobs"] == 1
    updated_job = service.get_job(job_id)
    assert updated_job["status"] == "SUBMITTED" and not updated_job["submission_verified"]
    assert "Python required." in updated_job["description"] and updated_job["last_changed"] != job["last_changed"]
    assert len(updated_job["history"]) == 2
    actions = {e["action"] for e in service.audit_events(100)}
    assert {"DISCOVERY_STARTED", "DISCOVERY_FINISHED", "LIVE_JOB_UPDATED", "LIVE_JOB_DISCOVERED"} <= actions


def test_unchanged_records_skip_normalization(system, monkeypatch):
    discovery, _ = system
    run(discovery)
    from job_agent.public_connectors import GreenhouseConnector, LeverConnector
    def unexpected(*args):
        raise AssertionError("unchanged record was normalized")
    monkeypatch.setattr(GreenhouseConnector, "normalize", unexpected)
    monkeypatch.setattr(LeverConnector, "normalize", unexpected)
    assert run(discovery)["metrics"]["unchanged_jobs"] == 2


def test_source_failure_isolation_and_safe_errors(system):
    discovery, state = system
    state["gh_status"] = 404
    result = run(discovery)
    assert result["status"] == "PARTIAL" and result["metrics"]["failed_sources"] == 1
    assert result["metrics"]["new_jobs"] == 1 and result["metrics"]["requests"] == 2
    sources = discovery.registry.list()
    assert sources[0]["health"] == "FAILED" and sources[0]["last_error"] == "board_not_found"
    assert sources[1]["health"] == "SUCCESS" and sources[1]["last_success"]
    assert result["sources"][0]["duration_seconds"] >= 0 and result["sources"][0]["started_at"] <= result["sources"][0]["finished_at"]


def test_record_rejection_and_source_partial(system):
    discovery, state = system
    state["gh"] = {"id": "bad", "title": "token=private"}
    result = run(discovery)
    assert result["metrics"]["rejected_records"] == 1 and result["metrics"]["new_jobs"] == 1
    assert result["sources"][0]["status"] == "PARTIAL"
    assert "private" not in str(JobService(discovery.db).audit_events(100))


def test_same_url_aliases_preserve_provenance_without_rejection(system):
    discovery, state = system
    run(discovery)
    state["gh"] = state["gh"] | {"id": 124}
    result = run(discovery)
    assert result["metrics"]["rejected_records"] == 0 and result["metrics"]["duplicates"]==1 and len(JobService(discovery.db).list_jobs()) == 1
    state["lever"] = state["lever"] | {"descriptionPlain": "Different requirements and Python"}
    result = run(discovery)
    assert result["metrics"]["rejected_records"] == 0


def test_seen_timestamps_and_metadata_only_change(system):
    discovery, state = system
    run(discovery)
    service = JobService(discovery.db)
    before = service.list_jobs()[0]
    state["gh"] = state["gh"] | {"updated_at": "2026-10-02T00:00:00Z"}
    result = run(discovery)
    after = service.list_jobs()[0]
    assert result["metrics"]["updated_jobs"] == 0 and result["metrics"]["unchanged_jobs"] == 2
    assert after["last_changed"] == before["last_changed"] and after["last_seen"] >= before["last_seen"]


def test_profile_and_background_rescore_live_without_listing_changes(system):
    discovery, _ = system
    run(discovery)
    service = JobService(discovery.db)
    job_id = service.list_jobs()[0]["id"]
    before = service.get_job(job_id)["last_changed"]
    service.save_profile(Profile(exclusions=["react"]))
    assert service.get_job(job_id)["match_score"] < 100
    service.save_background(SearchBackground(total_years=4, backend_years=3))
    assert service.get_job(job_id)["match"]["seniority_compatibility"] == "BELOW_STATED_MINIMUM"
    assert service.get_job(job_id)["last_changed"] == before


def test_registry_idempotence_toggles_and_identity(system):
    discovery, _ = system
    registry = discovery.registry
    assert registry.toggle("gh", False)
    registry.seed(config())
    assert not registry.list()[0]["enabled"]
    assert not registry.toggle("missing", True)
    registry.sync(config())
    assert registry.list()[0]["enabled"]
    with pytest.raises(ValueError, match="source_identity_immutable"):
        registry.sync(DiscoveryConfig(sources=[SourceConfig(id="gh", provider="greenhouse", company="Other", board="other")]))
    with pytest.raises(ValueError, match="duplicate_source_id"):
        registry.sync(DiscoveryConfig(sources=[config().sources[0]] * 2))


def test_run_lease_recovery_and_concurrent_claim(system):
    discovery, _ = system
    run_id = discovery.claim()
    other = Discovery(discovery.db, discovery.settings, discovery.client_factory)
    try:
        with pytest.raises(RunBusy):
            other.claim()
        with pytest.raises(ValueError, match="discovery_in_progress"):
            discovery.registry.sync(config())
        with discovery.db.transaction() as conn:
            conn.execute("UPDATE discovery_lease SET expires_at='2000-01-01'")
        recovered = other.claim()
        assert discovery.get_run(run_id)["status"] == "INTERRUPTED"
        assert other.execute(recovered)["status"] == "COMPLETED"
    finally:
        other.close()


def test_disabled_and_cooldown_skips(system):
    discovery, _ = system
    discovery.settings.cooldown_seconds = 3600
    run(discovery)
    result = run(discovery)
    assert result["metrics"]["requests"] == 0 and result["metrics"]["skipped_sources"] == 2
    discovery.registry.toggle("gh", False)
    discovery.registry.toggle("lever", False)
    assert run(discovery)["sources"] == []


def test_conditional_304_touch_and_cache_cooldown(system):
    discovery, _ = system
    run(discovery)
    def handler(request):
        return httpx.Response(304)
    with discovery.db.transaction() as conn:
        conn.execute("UPDATE sources SET checkpoint=?", (json.dumps({"complete": True, "pages": 1, "etag": "one", "cache-control": "max-age=60"}),))
    discovery.client_factory = lambda: httpx.Client(transport=httpx.MockTransport(handler))
    result = run(discovery)
    assert result["metrics"]["unchanged_jobs"] == 2
    assert run(discovery)["metrics"]["skipped_sources"] == 2


def test_budget_failure_and_internal_source_isolation(system, monkeypatch):
    discovery, _ = system
    discovery.settings.max_requests = 1
    result = run(discovery)
    assert result["metrics"]["requests"] == 1 and result["metrics"]["failed_sources"] == 1
    from job_agent.public_connectors import GreenhouseConnector
    monkeypatch.setattr(GreenhouseConnector, "fetch", lambda *args: (_ for _ in ()).throw(RuntimeError("private")))
    discovery.settings.max_requests = 20
    result = run(discovery)
    assert result["sources"][0]["error"] == "source_internal_error"


def test_background_api_nonblocking_and_overlap(tmp_path, greenhouse_record):
    entered, release = threading.Event(), threading.Event()
    def handler(request):
        entered.set()
        assert release.wait(5)
        return httpx.Response(200, json={"jobs": [greenhouse_record]})
    app = create_app(tmp_path / "state.sqlite3", DiscoveryConfig(settings=DiscoverySettings(cooldown_seconds=0), sources=[config().sources[0]]), lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    with TestClient(app) as client:
        try:
            started = time.monotonic()
            response = client.post("/api/discovery/runs")
            assert response.status_code == 202 and time.monotonic() - started < 2
            run_id = response.json()["run_id"]
            assert entered.wait(2)
            assert client.post("/api/discovery/runs").status_code == 409
            assert client.get(f"/api/discovery/runs/{run_id}").json()["status"] == "RUNNING"
        finally:
            release.set()
        app.state.discovery.executor.shutdown(wait=True)
        assert client.get("/api/discovery/latest").json()["status"] == "COMPLETED"
        jobs = client.get("/api/jobs?category=FRONTEND_LEADERSHIP&priority=P1&source=gh&sort=score_asc&kind=LIVE").json()
        assert len(jobs) == 1 and jobs[0]["listing_kind"] == "LIVE"
        assert client.patch("/api/sources/gh", json={"enabled": False}).status_code == 200
        assert client.patch("/api/sources/missing", json={"enabled": True}).status_code == 404
        assert client.get("/api/discovery/runs/missing").status_code == 404
        assert client.get("/api/search-background").json()["total_years"] == 0
        assert client.put("/api/search-background", json={"total_years": 6, "backend_years": 3}).status_code == 200
        assert client.post("/api/sources", json={"id": "other", "provider": "lever", "company": "Other", "board": "other"}).status_code == 200
        assert client.post("/api/sources", json={"id": "gh", "provider": "greenhouse", "company": "Other", "board": "other"}).status_code == 409
        assert client.get("/api/jobs?kind=SAMPLE").json() == []
        assert client.get("/api/jobs?kind=IMPORTED").json() == []
        assert client.get("/api/jobs?sort=last_seen").status_code == 200
        assert client.get("/api/jobs?category=INVALID").status_code == 422
        assert client.post("/api/submit", json={}).status_code == 404


def test_unknown_run_latest_and_failed_worker(system, monkeypatch):
    discovery, _ = system
    assert discovery.latest() is None and discovery.get_run("missing") is None
    discovery.close()
    with pytest.raises(RuntimeError):
        discovery.start()
    assert discovery.latest()["error"] == "worker_unavailable"
    def broken():
        raise RuntimeError("private")
    monkeypatch.setattr(discovery.registry, "list", broken)
    assert discovery.execute(discovery.claim())["error"] == "discovery_internal_error"


def test_config_validation_and_loading(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(config().model_dump_json())
    assert len(load_config(path).sources) == 2
    path.write_bytes(b"x" * 65537)
    with pytest.raises(ValueError, match="config_too_large"):
        load_config(path)
    for field in [{"board": "../evil"}, {"provider": "custom"}, {"id": "https://evil"}]:
        with pytest.raises(ValueError):
            SourceConfig(**(dict(id="a", provider="lever", company="Acme", board="acme") | field))
    with pytest.raises(ValueError):
        DiscoverySettings(concurrency_limit=9)
    with pytest.raises(ValueError, match="unsupported_greenhouse_region"):
        SourceConfig(id="eu", provider="greenhouse", company="Acme", board="acme", region="eu")
    assert future_timestamp(1e100).startswith("9999-")


def test_migration_backup_preserves_v1_and_reopen(tmp_path):
    path = tmp_path / "old.sqlite3"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.execute("PRAGMA user_version=1")
    conn.execute("INSERT INTO candidate_profile VALUES (1, ?, 'old')", (Profile(experience_years=4).model_dump_json(),))
    conn.commit()
    conn.close()
    db = Database(path)
    assert JobService(db).get_profile()["experience_years"] == 4
    assert path.with_suffix(".sqlite3.pre-v2.bak").exists()
    with sqlite3.connect(path.with_suffix(".sqlite3.pre-v2.bak")) as backup:
        assert backup.execute("PRAGMA user_version").fetchone()[0] == 1
    with db.transaction() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 17
    Database(path)


def test_migration_rolls_back_and_rejects_unknown_version(tmp_path, monkeypatch):
    import job_agent.migrations as migrations
    path = tmp_path / "old.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA)
        conn.execute("PRAGMA user_version=1")
        monkeypatch.setattr(migrations, "STATEMENTS", ["INVALID SQL"])
        with pytest.raises(sqlite3.OperationalError):
            migrate(conn, path)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
        assert "category" not in [row[1] for row in conn.execute("PRAGMA table_info(jobs)")]
        conn.execute("PRAGMA user_version=99")
        with pytest.raises(RuntimeError, match="unsupported_database_version"):
            migrate(conn, path)

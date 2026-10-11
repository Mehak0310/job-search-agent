import sqlite3

import pytest

from job_agent.database import Database
from job_agent.models import Profile, Status
from job_agent.service import JobService


def test_import_idempotency_and_provenance(app, record):
    service = app.state.service
    first = service.import_rows([record])
    assert (first["created"], first["references_added"], first["invalid"]) == (1, 1, 0)
    repeated = service.import_rows([record, record])
    assert repeated["duplicates"] == 2 and repeated["references_added"] == 0
    cross_source = service.import_rows([record | {"source": "other", "source_job_id": "different"}])
    assert cross_source["duplicates"] == 1 and cross_source["references_added"] == 1
    job = service.get_job(service.list_jobs()[0]["id"])
    assert len(job["sources"]) == 2 and len(job["history"]) == 1
    assert any(e["action"] == "DUPLICATE_DETECTED" for e in service.audit_events())


def test_partial_invalid_records_and_no_sensitive_audit(app, record):
    service = app.state.service
    report = service.import_rows([record, {"token": "super-secret"}, 42, record | {"description": "changed"}])
    assert report["created"] == 1 and report["invalid"] == 3
    assert report["errors"][-1]["code"] == "content_conflict"
    assert "super-secret" not in str(report) + str(service.audit_events())
    assert "token" not in str(report)


def test_conflicting_identity_and_alias_url(app, record):
    service = app.state.service
    service.import_rows([record])
    assert service.import_rows([record | {"title": "Other"}])["errors"][0]["code"] == "identity_conflict"
    # New provenance URL is retained without changing canonical job data.
    assert service.import_rows([record | {"source": "other", "application_url": "https://example.org/alias"}])["references_added"] == 1
    assert service.import_rows([record | {"source": "third", "title": "Other", "application_url": "https://example.org/alias"}])["invalid"] == 1
    second = record | {"source_job_id": "two", "title": "Applied AI Engineer", "application_url": "https://example.com/two"}
    service.import_rows([second])
    conflict = record | {"source": "third", "application_url": "https://example.com/two"}
    assert service.import_rows([conflict])["errors"][0]["code"] == "identity_conflict"


def test_source_identifier_reuse(app, record):
    service = app.state.service
    service.import_rows([record | {"application_url": None}])
    assert service.import_rows([record | {"title": "Changed", "application_url": None}])["invalid"] == 1


def test_no_source_id_and_case_normalization(app, record):
    service = app.state.service
    service.import_rows([record | {"source_job_id": None, "application_url": None}])
    assert service.import_rows([record | {"source_job_id": None, "application_url": None, "source": "FIXTURE"}])["duplicates"] == 1
    normalized = record | {"source_job_id": None, "application_url": None, "company": " EXAMPLE ", "title": "ai engineer", "location": "INDIA", "work_mode": "REMOTE", "skills": [" PYTHON "]}
    assert service.import_rows([normalized])["duplicates"] == 1


def test_manual_status_history_persistence_and_profile(tmp_path, record):
    path = tmp_path / "persistent.sqlite3"
    service = JobService(Database(path))
    service.import_rows([record])
    job_id = service.list_jobs()[0]["id"]
    assert not service.set_status("missing", Status.OFFER)
    assert service.get_job("missing") is None
    for status in Status:
        assert service.set_status(job_id, status)
    count = len(service.get_job(job_id)["history"])
    service.set_status(job_id, Status.OFFER)
    assert len(service.get_job(job_id)["history"]) == count
    service.save_profile(Profile(experience_years=3))
    reopened = JobService(Database(path))
    assert reopened.get_profile()["experience_years"] == 3
    job = reopened.get_job(job_id)
    assert job["status"] == "OFFER" and not job["submission_verified"]
    assert job["match_score"] == 100
    assert any(e["action"] == "PROFILE_UPDATED" for e in reopened.audit_events())


def test_search_filters_and_literal_wildcards(app, record):
    service = app.state.service
    service.import_rows([record | {"company": "Example_100%"}])
    job_id = service.list_jobs()[0]["id"]
    service.set_status(job_id, Status.SHORTLISTED)
    assert len(service.list_jobs("AI", "SHORTLISTED", "remote", 50)) == 1
    assert len(service.list_jobs("_100%")) == 1
    assert service.list_jobs("' OR 1=1 --") == []
    assert service.list_jobs(status="NEW") == []
    assert service.list_jobs(work_mode="onsite") == []


@pytest.mark.parametrize("table", ["audit_events", "status_history"])
@pytest.mark.parametrize("operation", ["UPDATE {table} SET created_at='changed'", "DELETE FROM {table}"])
def test_append_only(app, record, table, operation):
    service = app.state.service
    service.import_rows([record])
    with pytest.raises(sqlite3.IntegrityError, match="append_only"):
        with service.db.transaction() as conn:
            conn.execute(operation.format(table=table))


def test_transaction_rolls_back_job_and_audit(app, record, monkeypatch):
    service = app.state.service
    def fail(*args):
        raise RuntimeError("simulated audit failure")
    monkeypatch.setattr(service.db, "audit", fail)
    with pytest.raises(RuntimeError):
        service.import_rows([record])
    assert service.list_jobs() == []
    with service.db.transaction() as conn:
        assert conn.execute("SELECT COUNT(*) FROM source_references").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM status_history").fetchone()[0] == 0


def test_status_transaction_rolls_back(app, record, monkeypatch):
    service = app.state.service
    service.import_rows([record])
    job_id = service.list_jobs()[0]["id"]
    monkeypatch.setattr(service.db, "audit", lambda *args: (_ for _ in ()).throw(RuntimeError()))
    with pytest.raises(RuntimeError):
        service.set_status(job_id, Status.SUBMITTED)
    assert service.get_job(job_id)["status"] == "NEW"

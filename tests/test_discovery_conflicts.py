import httpx

from job_agent.candidate import SearchBackground
from job_agent.database import Database
from job_agent.discovery import Discovery
from job_agent.discovery_models import DiscoverySettings, SourceConfig, metrics
from job_agent.discovery_store import persist_batch
from job_agent.models import Profile
from job_agent.public_connectors import GreenhouseConnector, LeverConnector, RequestBudget
from job_agent.service import JobService


def persist(db, source, records, connector=None):
    counters = metrics()
    persist_batch(db, source, connector or GreenhouseConnector(), records, SearchBackground(), Profile(), counters, RequestBudget(DiscoverySettings()))
    return counters


def test_invalid_ids_and_normalized_id_mismatch(tmp_path, greenhouse_record):
    db = Database(tmp_path / "state.sqlite3")
    source = SourceConfig(id="gh", provider="greenhouse", company="Acme", board="acme")
    records = [None, {}, greenhouse_record | {"id": True}, greenhouse_record | {"id": " 123 "}, greenhouse_record, greenhouse_record]
    result = persist(db, source, records)
    assert result["new_jobs"] == 1 and result["rejected_records"] == 4 and result["duplicates"]==1


def test_distinct_requisitions_and_exact_url_aliases(tmp_path, greenhouse_record):
    db = Database(tmp_path / "state.sqlite3")
    source = SourceConfig(id="gh", provider="greenhouse", company="Acme", board="acme")
    persist(db, source, [greenhouse_record, greenhouse_record | {"id": 456, "title": "Senior React Developer", "absolute_url": "https://example.com/jobs/456"}])
    third = SourceConfig(id="third", provider="greenhouse", company="Acme", board="third")
    result=persist(db, third, [greenhouse_record | {"absolute_url": "https://example.com/jobs/456"}])
    assert result["rejected_records"] == 0 and result["duplicates"]==1
    assert len(JobService(db).list_jobs()) == 2


def test_sample_identity_cannot_be_replaced_by_live(tmp_path, greenhouse_record):
    db = Database(tmp_path / "state.sqlite3")
    source = SourceConfig(id="gh", provider="greenhouse", company="Acme", board="acme")
    job, _, _ = GreenhouseConnector().normalize(source, greenhouse_record)
    JobService(db).import_rows([job.model_dump(mode="json") | {"source": "sample", "is_sample": True}])
    assert persist(db, source, [greenhouse_record])["rejected_records"] == 1
    assert JobService(db).list_jobs()[0]["listing_kind"] == "SAMPLE"


def test_new_cross_source_content_is_retained_as_alias_evidence(tmp_path, greenhouse_record):
    db = Database(tmp_path / "state.sqlite3")
    source = SourceConfig(id="gh", provider="greenhouse", company="Acme", board="acme")
    persist(db, source, [greenhouse_record])
    other = SourceConfig(id="other", provider="greenhouse", company="Acme", board="other")
    result = persist(db, other, [greenhouse_record | {"content": "Different"}])
    assert result["rejected_records"] == 0 and result["duplicates"] == 1


def test_sample_api_source_health_latest(client):
    sources = client.get("/api/sources").json()
    assert {source["provider"] for source in sources} == {"greenhouse", "lever", "remoteok", "wwr", "smartrecruiters", "amazon"}
    assert all(source["health"] == "UNSCANNED" and source["last_success"] is None for source in sources)

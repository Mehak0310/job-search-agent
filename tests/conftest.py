import pytest
import httpx
from fastapi.testclient import TestClient

from job_agent.main import create_app


@pytest.fixture(autouse=True)
def forbid_live_http(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Real HTTP transport is forbidden in automated tests; inject MockTransport")
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)


@pytest.fixture
def record():
    return {"source": "fixture", "source_job_id": "one", "company": "Example", "title": "AI Engineer", "location": "India", "work_mode": "remote", "description": "Fictional", "skills": ["Python"], "application_url": "https://example.com/one", "min_experience": 2, "max_experience": 5, "is_sample": True}


@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path / "state.sqlite3")


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


@pytest.fixture
def greenhouse_record():
    return {"id": 123, "title": "Frontend Technical Lead", "location": {"name": "Bengaluru, India (Hybrid)"}, "absolute_url": "https://example.com/jobs/123", "content": "<h3>Requirements</h3><p>React and TypeScript required.</p><p>5+ years of professional experience</p>", "updated_at": "2026-10-01T00:00:00Z"}


@pytest.fixture
def lever_record(greenhouse_record):
    return {"id": "abc", "text": greenhouse_record["title"], "categories": {"location": greenhouse_record["location"]["name"]}, "descriptionPlain": "Requirements\nReact and TypeScript required.\n5+ years of professional experience", "hostedUrl": greenhouse_record["absolute_url"], "applyUrl": greenhouse_record["absolute_url"], "workplaceType": "hybrid"}

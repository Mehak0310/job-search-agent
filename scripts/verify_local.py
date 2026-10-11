"""Verify an already-running loopback server using fictional jobs only."""
import argparse
from pathlib import Path

import httpx

from job_agent.database import Database
from job_agent.service import JobService


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    with httpx.Client(base_url=f"http://127.0.0.1:{args.port}", trust_env=False, timeout=10) as client:
        assert client.get("/api/health").json()["status"] == "ok"
        html = client.get("/")
        assert html.status_code == 200 and "Job Search Workspace" in html.text
        for asset in ("app.js", "style.css"):
            assert client.get("/static/" + asset).status_code == 200
        payload = Path("samples/jobs.json").read_bytes()
        first = client.post("/api/import", files={"file": ("jobs.json", payload)})
        first.raise_for_status()
        assert first.json()["invalid"] == 0
        repeated = client.post("/api/import", files={"file": ("jobs.json", payload)}).json()
        assert repeated["created"] == 0 and repeated["duplicates"] == 3
        csv = client.post("/api/import", files={"file": ("jobs.csv", Path("samples/jobs.csv").read_bytes())}).json()
        assert csv["invalid"] == 0
        jobs = client.get("/api/jobs?q=Example&min_score=0").json()
        samples = [job for job in jobs if job["is_sample"]]
        assert len(samples) == 4
        job = next(j for j in samples if j["company"] == "Example AI Labs (fictional)")
        job_id = job["id"]
        detail = client.get(f"/api/jobs/{job_id}").json()
        assert len(detail["sources"]) == 2 and detail["match"]["reasons"]
        changed = client.patch(f"/api/jobs/{job_id}/status", json={"status": "SHORTLISTED"})
        changed.raise_for_status()
        assert changed.json()["status"] == "SHORTLISTED"
        assert not changed.json()["submission_verified"]
        # Reopen persisted SQLite state independently from the server.
        persisted = JobService(Database("data/jobs.sqlite3")).get_job(job_id)
        assert persisted["status"] == "SHORTLISTED"
        events = client.get("/api/audit?limit=100").json()
        assert any(event["action"] == "STATUS_CHANGED" for event in events)
        assert client.post("/api/submit", json={}).status_code == 404
        print("PASS: health, rendered HTML, static assets, JSON/CSV imports, idempotency, provenance, explained matching, manual shortlist, persisted SQLite state, audit and absent submission endpoint")
        print(f"Dashboard verified: http://127.0.0.1:{args.port}/")
        print(f"Fictional jobs: {len(samples)}; match scores: {[j['match_score'] for j in samples]}")


if __name__ == "__main__":
    main()

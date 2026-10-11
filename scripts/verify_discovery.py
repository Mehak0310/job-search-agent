"""Bounded live integration check; public listings only, never submission."""
import argparse
import json
from collections import Counter
from pathlib import Path

from job_agent.database import Database
from job_agent.discovery import Discovery
from job_agent.registry import Registry, load_config
from job_agent.service import JobService


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeat", action="store_true")
    args = parser.parse_args()
    db = Database("data/jobs.sqlite3")
    service = JobService(db)
    cfg = load_config("config/discovery.json")
    Registry(db).seed(cfg)
    report_path = Path("data/milestone-2a-live-verification.json")
    if args.repeat:
        report = json.loads(report_path.read_text())
    else:
        report = {"baseline": {job["id"]: {"status": job["status"], "history_count": len(service.get_job(job["id"])["history"])} for job in service.list_jobs()}}
    settings = cfg.settings.model_copy(update={"max_requests": 6, "max_runtime_seconds": 60, "retry_limit": 1, "cooldown_seconds": 0})
    discovery = Discovery(db, settings)
    try:
        result = discovery.execute(discovery.claim())
    finally:
        discovery.close()
    for job_id, old in report["baseline"].items():
        current = service.get_job(job_id)
        assert current["status"] == old["status"] and len(current["history"]) == old["history_count"]
    with db.transaction() as conn:
        live = [dict(row) for row in conn.execute("SELECT category, match_detail, status FROM jobs WHERE is_sample=0 AND discovery_detail IS NOT NULL")]
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    summary = {"run": result, "real_jobs": len(live), "categories": dict(Counter(row["category"] for row in live)), "eligibility": dict(Counter(json.loads(row["match_detail"])["location_eligibility"] for row in live)), "statuses_preserved": True, "submission_enabled": False}
    report["repeat" if args.repeat else "first"] = summary
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("SOURCE HEALTH:", json.dumps([{k: source[k] for k in ("id", "health", "last_success", "last_error", "next_scan_after")} for source in Registry(db).list()], indent=2))
    if result["metrics"]["failed_sources"]:
        raise SystemExit(1)
    if args.repeat:
        assert summary["real_jobs"] == report["first"]["real_jobs"]
        assert result["metrics"]["new_jobs"] == 0


if __name__ == "__main__":
    main()

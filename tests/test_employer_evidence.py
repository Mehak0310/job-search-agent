from datetime import datetime, timedelta, timezone

import pytest

from job_agent.employer_evidence import reuse_large_employer_check
from job_agent.m2d import M2DEngine
from tests.test_m3 import setup_engine


@pytest.mark.parametrize(
    "work_mode,count,expected",
    [
        ("hybrid", 500, "UNKNOWN"),
        ("hybrid", 999, "UNKNOWN"),
        ("hybrid", 1000, "PASS"),
        ("remote", 499, "UNKNOWN"),
        ("remote", 500, "PASS"),
    ],
)
def test_reused_headcount_uses_role_threshold_and_keeps_original_verification_time(
    tmp_path, work_mode, count, expected
):
    db, _, job_id = setup_engine(tmp_path)
    url = "https://careers.example.test/company"
    verified_at = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    M2DEngine(db).record_evidence(
        job_id,
        "headcount",
        "PASS",
        factual=f"Global workforce of {count:,} employees.",
        evidence_url=url,
        verified_at=verified_at,
    )
    with db.transaction() as conn:
        conn.execute("UPDATE jobs SET work_mode=? WHERE id=?", (work_mode, job_id))
        conn.execute(
            "UPDATE job_operational_state SET headcount_state='UNKNOWN' WHERE job_id=?",
            (job_id,),
        )
        row = dict(
            conn.execute(
                """SELECT j.*,s.job_key,s.headcount_state,s.missing_facts
                   FROM jobs j JOIN job_operational_state s ON s.job_id=j.id WHERE j.id=?""",
                (job_id,),
            ).fetchone()
        )

    result = reuse_large_employer_check(db, row)
    with db.transaction() as conn:
        stored = conn.execute(
            "SELECT headcount_state FROM job_operational_state WHERE job_id=?",
            (job_id,),
        ).fetchone()[0]
        evidence_time = conn.execute(
            "SELECT verified_at FROM job_evidence WHERE job_key=? AND kind='headcount'",
            (job_id,),
        ).fetchone()[0]
    assert stored == expected
    assert result["headcount_state"] == expected
    if expected == "PASS":
        assert evidence_time == verified_at


@pytest.mark.parametrize(
    "age_delta,expected_state",
    [
        (timedelta(days=90), "PASS"),
        (timedelta(days=90, seconds=1), "UNKNOWN"),
        (-timedelta(seconds=1), "UNKNOWN"),
    ],
)
def test_reuse_obeys_exact_freshness_boundary_and_rejects_future_evidence(
    tmp_path, age_delta, expected_state
):
    fixed_now = datetime(2026, 10, 19, 12, tzinfo=timezone.utc)
    db, _, job_key = setup_engine(tmp_path)
    verified_at = (fixed_now - age_delta).isoformat()
    url = "https://careers.example.test/company"
    M2DEngine(db).record_evidence(
        job_key,
        "headcount",
        "PASS",
        factual="Global workforce of 1,000 employees.",
        evidence_url=url,
        verified_at=verified_at,
    )
    with db.transaction() as conn:
        conn.execute("UPDATE job_operational_state SET headcount_state='UNKNOWN' WHERE job_id=?", (job_key,))
        row = dict(
            conn.execute(
                """SELECT j.*,s.job_key,s.headcount_state,s.missing_facts
                   FROM jobs j JOIN job_operational_state s ON s.job_id=j.id WHERE j.id=?""",
                (job_key,),
            ).fetchone()
        )

    result = reuse_large_employer_check(db, row, at=fixed_now)
    assert result["headcount_state"] == expected_state
    with db.transaction() as conn:
        stored_time = conn.execute(
            "SELECT verified_at FROM job_evidence WHERE job_key=? AND kind='headcount'",
            (job_key,),
        ).fetchone()[0]
    assert stored_time == verified_at


def test_reuse_does_not_turn_threshold_crossing_range_into_pass(tmp_path):
    fixed_now = datetime(2026, 10, 19, 12, tzinfo=timezone.utc)
    db, _, job_key = setup_engine(tmp_path)
    M2DEngine(db).record_evidence(
        job_key,
        "headcount",
        "PASS",
        factual="Global workforce of 800-1,200 employees.",
        evidence_url="https://careers.example.test/company",
        verified_at=(fixed_now - timedelta(days=1)).isoformat(),
    )
    with db.transaction() as conn:
        conn.execute("UPDATE job_operational_state SET headcount_state='UNKNOWN' WHERE job_id=?", (job_key,))
        row = dict(
            conn.execute(
                """SELECT j.*,s.job_key,s.headcount_state,s.missing_facts
                   FROM jobs j JOIN job_operational_state s ON s.job_id=j.id WHERE j.id=?""",
                (job_key,),
            ).fetchone()
        )

    assert reuse_large_employer_check(db, row, at=fixed_now)["headcount_state"] == "UNKNOWN"

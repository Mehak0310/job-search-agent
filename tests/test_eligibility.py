from datetime import datetime, timedelta, timezone

import pytest

from job_agent.eligibility import assess_hard_eligibility


AT = datetime(2026, 10, 19, 12, tzinfo=timezone.utc)
URL = "https://careers.example.test/jobs/123"


def evidence(kind, factual, *, state="PASS", days_old=1, url=URL):
    return {
        "kind": kind,
        "state": state,
        "factual": factual,
        "evidence_url": url,
        "verified_at": (AT - timedelta(days=days_old)).isoformat(),
    }


def eligible_evidence(headcount="1,000 employees", *, days_old=1):
    return [
        evidence("active", "Vacancy is active and open for applications.", days_old=days_old),
        evidence("india_eligible", "Employer explicitly supports employment in India.", days_old=days_old),
        evidence("headcount", f"Global workforce of {headcount}.", days_old=days_old),
        evidence(
            "direct_permanent_payroll",
            "India employees are hired directly on permanent full-time payroll.",
            days_old=days_old,
        ),
    ]


def job(*, mode="hybrid", location="Noida, India"):
    return {
        "company": "Example",
        "title": "Frontend Engineer",
        "work_mode": mode,
        "location": location,
        "application_url": URL,
        "canonical_application_url": URL,
    }


def references(days_old=1):
    return [
        {
            "listing_url": URL,
            "application_url": URL,
            "last_seen": (AT - timedelta(days=days_old)).isoformat(),
            "imported_at": (AT - timedelta(days=days_old)).isoformat(),
        }
    ]


@pytest.mark.parametrize(
    "mode,location,count,expected",
    [
        ("remote", "India remote", "500 employees", "PASS"),
        ("remote", "India remote", "499 employees", "FAIL"),
        ("hybrid", "Noida, India", "1,000 employees", "PASS"),
        ("hybrid", "Noida, India", "999 employees", "FAIL"),
    ],
)
def test_headcount_thresholds_are_mode_specific(mode, location, count, expected):
    facts = eligible_evidence(count)
    if expected == "FAIL":
        facts[2]["state"] = "FAIL"
    result = assess_hard_eligibility(
        job(mode=mode, location=location),
        facts,
        references(),
        at=AT,
    )
    assert result["gates"]["employer_size"]["state"] == expected
    assert result["state"] == expected


def test_missing_stale_and_unverifiable_evidence_stay_unknown():
    assert assess_hard_eligibility(job(), [], references(), at=AT)["state"] == "UNKNOWN"
    stale = eligible_evidence(days_old=8)
    result = assess_hard_eligibility(job(), stale, references(days_old=8), at=AT)
    assert result["state"] == "UNKNOWN"
    assert "stale" in result["gates"]["active"]["reason"]
    private_url = eligible_evidence()
    private_url[0]["evidence_url"] = "https://user:secret@careers.example.test/jobs/123"
    result = assess_hard_eligibility(job(), private_url, references(), at=AT)
    assert result["gates"]["active"]["state"] == "UNKNOWN"


def test_employer_evidence_uses_ninety_day_expiry_independently():
    facts = eligible_evidence()
    facts = [evidence(item["kind"],item["factual"],days_old=91) if item["kind"]!="active" else item for item in facts]
    result = assess_hard_eligibility(job(), facts, references(), at=AT)
    assert result["gates"]["active"]["state"] == "PASS"
    assert result["gates"]["india_employment"]["state"] == "UNKNOWN"
    assert result["gates"]["employer_size"]["state"] == "UNKNOWN"
    assert result["gates"]["payroll"]["state"] == "UNKNOWN"


def test_malformed_provenance_and_headcount_ranges_fail_closed():
    facts = eligible_evidence("800-1,200 employees")
    facts[0]["verified_at"] = "not-a-timestamp"
    facts[1]["evidence_url"] = "https://["
    result = assess_hard_eligibility(job(), facts, references(), at=AT.replace(tzinfo=None))
    assert result["gates"]["active"]["state"] == "UNKNOWN"
    assert result["gates"]["india_employment"]["state"] == "UNKNOWN"
    assert result["gates"]["employer_size"]["state"] == "UNKNOWN"


def test_explicit_current_failure_is_a_blocking_verdict():
    facts = eligible_evidence()
    facts[0] = evidence("active", "Vacancy is closed.", state="FAIL")
    result = assess_hard_eligibility(job(), facts, references(), at=AT)
    assert result["gates"]["active"]["state"] == "FAIL"
    assert result["state"] == "FAIL"


def test_conflicting_evidence_and_unsubstantiated_pass_do_not_pass():
    facts = eligible_evidence()
    facts.append(evidence("india_eligible", "Employer does not hire in India.", state="FAIL"))
    result = assess_hard_eligibility(job(), facts, references(), at=AT)
    assert result["state"] == "CONFLICT"
    assert result["gates"]["india_employment"]["state"] == "CONFLICT"
    facts = eligible_evidence()
    facts[0]["factual"] = "The employer website was checked."
    result = assess_hard_eligibility(job(), facts, references(), at=AT)
    assert result["gates"]["active"]["state"] == "UNKNOWN"
    facts = eligible_evidence()
    facts[0]["factual"] = "The vacancy is not active."
    result = assess_hard_eligibility(job(), facts, references(), at=AT)
    assert result["gates"]["active"]["state"] == "CONFLICT"


@pytest.mark.parametrize(
    "mode,location,expected",
    [
        ("hybrid", "Noida, India", "PASS"),
        ("hybrid", "Pune, India", "FAIL"),
        ("remote", "India remote", "PASS"),
        ("remote", "Worldwide", "UNKNOWN"),
    ],
)
def test_supported_location_is_explicit_and_current(mode, location, expected):
    result = assess_hard_eligibility(
        job(mode=mode, location=location),
        eligible_evidence("1,000 employees" if mode != "remote" else "500 employees"),
        references(),
        at=AT,
    )
    assert result["gates"]["location"]["state"] == expected


@pytest.mark.parametrize(
    "mode,location,expected",
    [
        ("hybrid", "Noida, Canada", "FAIL"),
        ("hybrid", "Noida, India / Toronto, Canada", "UNKNOWN"),
        ("remote", "India remote, USA", "UNKNOWN"),
        ("hybrid", "Noida / Gurugram, India", "PASS"),
        ("hybrid", "Noida / Pune, India", "UNKNOWN"),
        ("hybrid", ["Noida, India", "Pune, India"], "UNKNOWN"),
        ("unknown", "Noida, India", "UNKNOWN"),
        ("hybrid", "Noida", "UNKNOWN"),
    ],
)
def test_location_requires_unambiguous_country_and_work_mode(mode, location, expected):
    result = assess_hard_eligibility(
        job(mode=mode, location=location),
        eligible_evidence("1,000 employees"),
        references(),
        at=AT,
    )
    assert result["gates"]["location"]["state"] == expected


def test_freshness_boundaries_accept_offsets_and_reject_future_evidence():
    facts = eligible_evidence()
    for item in facts:
        days = 7 if item["kind"] == "active" else 90
        offset = timezone(timedelta(hours=-5 if item["kind"] == "active" else 5, minutes=30))
        item["verified_at"] = (AT - timedelta(days=days)).astimezone(offset).isoformat()
    refs = references()
    refs[0]["last_seen"] = (AT - timedelta(days=7)).astimezone(timezone(timedelta(hours=5, minutes=30))).isoformat()
    assert assess_hard_eligibility(job(location="Noida, India"), facts, refs, at=AT)["state"] == "PASS"

    facts[0]["verified_at"] = (AT + timedelta(seconds=1)).isoformat()
    result = assess_hard_eligibility(job(location="Noida, India"), facts, refs, at=AT)
    assert result["gates"]["active"]["state"] == "UNKNOWN"
    assert result["state"] == "UNKNOWN"


@pytest.mark.parametrize("kind,max_age", [("active", 7), ("india_eligible", 90), ("headcount", 90), ("direct_permanent_payroll", 90)])
def test_each_evidence_kind_expires_after_its_exact_freshness_window(kind, max_age):
    facts = eligible_evidence()
    stale_item = next(item for item in facts if item["kind"] == kind)
    stale_item["verified_at"] = (AT - timedelta(days=max_age, seconds=1)).isoformat()
    result = assess_hard_eligibility(job(), facts, references(), at=AT)
    gate = {
        "active": "active",
        "india_eligible": "india_employment",
        "headcount": "employer_size",
        "direct_permanent_payroll": "payroll",
    }[kind]
    assert result["gates"][gate]["state"] == "UNKNOWN"


@pytest.mark.parametrize("kind", ["active", "india_eligible", "headcount", "direct_permanent_payroll"])
@pytest.mark.parametrize("timestamp", [None, "malformed-timestamp"])
def test_missing_or_malformed_evidence_timestamps_require_verification(kind, timestamp):
    facts = eligible_evidence()
    item = next(item for item in facts if item["kind"] == kind)
    item["verified_at"] = timestamp
    result = assess_hard_eligibility(job(), facts, references(), at=AT)
    gate = {
        "active": "active",
        "india_eligible": "india_employment",
        "headcount": "employer_size",
        "direct_permanent_payroll": "payroll",
    }[kind]
    assert result["gates"][gate]["state"] == "UNKNOWN"


@pytest.mark.parametrize(
    "kind,factual,state,expected",
    [
        ("india_eligible", "Employer explicitly supports employment in India.", "PASS", "PASS"),
        ("india_eligible", "Employer does not support employment in India.", "FAIL", "FAIL"),
        ("india_eligible", "India appears in a region list.", "PASS", "UNKNOWN"),
        ("india_eligible", "Employer supports employment in India but does not support employment in India.", "PASS", "CONFLICT"),
        ("direct_permanent_payroll", "Employees are hired directly on permanent full-time payroll.", "PASS", "PASS"),
        ("direct_permanent_payroll", "Contractor role; payroll is through a vendor.", "FAIL", "FAIL"),
        ("direct_permanent_payroll", "Direct and permanent are listed in the role description.", "PASS", "UNKNOWN"),
        ("direct_permanent_payroll", "Employees are hired directly on full-time payroll.", "PASS", "UNKNOWN"),
        ("direct_permanent_payroll", "Employees are hired directly on permanent payroll; contract role.", "PASS", "CONFLICT"),
    ],
)
def test_india_and_payroll_evidence_is_fail_closed(kind, factual, state, expected):
    facts = eligible_evidence()
    item = evidence(kind, factual, state=state)
    facts = [item if current["kind"] == kind else current for current in facts]
    result = assess_hard_eligibility(job(location="Noida, India"), facts, references(), at=AT)
    gate = "india_employment" if kind == "india_eligible" else "payroll"
    assert result["gates"][gate]["state"] == expected


def test_malformed_factual_text_cannot_raise_or_pass():
    facts = eligible_evidence()
    facts[1]["factual"] = {"claim": "supports India"}
    result = assess_hard_eligibility(job(location="Noida, India"), facts, references(), at=AT)
    assert result["gates"]["india_employment"]["state"] == "UNKNOWN"
    assert result["state"] == "UNKNOWN"


@pytest.mark.parametrize(
    "mode,factual,state,expected",
    [
        ("hybrid", "Global workforce of 800-1,200 employees.", "PASS", "UNKNOWN"),
        ("hybrid", "Global workforce of 900-999 employees.", "FAIL", "FAIL"),
        ("hybrid", "Global workforce of 1,000-1,200 employees.", "PASS", "PASS"),
        ("remote", "Global workforce of 500-700 employees.", "PASS", "PASS"),
        ("remote", "Global workforce of 400-499 employees.", "FAIL", "FAIL"),
        ("remote", "Global workforce of 400-600 employees.", "PASS", "UNKNOWN"),
        ("remote", "Global workforce size unavailable.", "PASS", "UNKNOWN"),
    ],
)
def test_headcount_ranges_are_interpreted_conservatively(mode, factual, state, expected):
    facts = eligible_evidence()
    facts[2] = evidence("headcount", factual, state=state)
    result = assess_hard_eligibility(job(mode=mode, location="India remote" if mode == "remote" else "Noida, India"), facts, references(), at=AT)
    assert result["gates"]["employer_size"]["state"] == expected


def test_headcount_text_contradicting_stored_pass_requires_verification():
    facts = eligible_evidence()
    facts[2]["factual"] = "Global workforce of 999 employees."
    result = assess_hard_eligibility(job(), facts, references(), at=AT)
    assert result["gates"]["employer_size"]["state"] == "CONFLICT"

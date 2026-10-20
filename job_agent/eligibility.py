"""Deterministic eligibility gates backed by recent, sourced evidence."""
from datetime import datetime, timedelta, timezone
import re
from urllib.parse import urlsplit


VACANCY_EVIDENCE_DAYS = 7
EMPLOYER_EVIDENCE_DAYS = 90
_ALLOWED_LOCATIONS = (
    "delhi ncr",
    "noida",
    "gurugram",
    "gurgaon",
    "greater noida",
    "mohali",
    "chandigarh",
)
_HEADCOUNT = re.compile(
    r"(?i)(?<!\w)(\d{1,3}(?:,\d{3})+|\d{3,})\s*(?:\+|employees?\b|staff\b|people\b|workforce\b|headcount\b)"
)
_HEADCOUNT_RANGE = re.compile(
    r"(?i)(?<!\w)(\d{1,3}(?:,\d{3})+|\d{3,})\s*(?:-|to)\s*(\d{1,3}(?:,\d{3})+|\d{3,})\s*(?:employees?\b|staff\b|people\b|workforce\b|headcount\b)"
)
_HEADCOUNT_PREFIX = re.compile(
    r"(?i)\b(?:employee count|headcount|workforce)\b\D{0,24}(\d{1,3}(?:,\d{3})+|\d{3,})"
)
_HEADCOUNT_RANGE_ANY = re.compile(
    r"(?i)(?<!\w)(\d{1,3}(?:,\d{3})+|\d{3,})\s*(?:-|to)\s*(\d{1,3}(?:,\d{3})+|\d{3,})"
)
_FOREIGN_COUNTRY = re.compile(
    r"(?i)\b(?:US|USA|United States|Canada|United Kingdom|UK|Europe|Singapore|Australia|Germany|France|"
    r"Ireland|Netherlands|Japan|China|Brazil|Mexico|Philippines|South Africa|United Arab Emirates|UAE)\b"
)


def _timestamp(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _https_url(value):
    try:
        parsed = urlsplit(value or "")
        return parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username and not parsed.password
    except (TypeError, ValueError):
        return False


def _current_evidence(rows, kind, at, max_age):
    cutoff = at - timedelta(days=max_age)
    return [
        row
        for row in rows
        if row.get("kind") == kind
        and row.get("state") in {"PASS", "FAIL"}
        and isinstance(row.get("factual"), str)
        and bool(row.get("factual"))
        and _https_url(row.get("evidence_url"))
        and (stamp := _timestamp(row.get("verified_at"))) is not None
        and cutoff <= stamp <= at
    ]


def _headcount_verdict(factual, threshold):
    factual = factual or ""
    ranges = [
        (int(low.replace(",", "")), int(high.replace(",", "")))
        for low, high in _HEADCOUNT_RANGE.findall(factual)
    ]
    without_ranges = _HEADCOUNT_RANGE_ANY.sub(" ", factual)
    counts = [
        int(value.replace(",", ""))
        for value in _HEADCOUNT.findall(without_ranges) + _HEADCOUNT_PREFIX.findall(without_ranges)
    ]
    if any(low > high for low, high in ranges):
        return "UNKNOWN"
    outcomes = [
        "PASS" if low >= threshold else "FAIL" if high < threshold else "UNKNOWN"
        for low, high in ranges
    ]
    outcomes.extend("PASS" if count >= threshold else "FAIL" for count in counts)
    if not outcomes or "UNKNOWN" in outcomes or len(set(outcomes)) > 1:
        return "UNKNOWN"
    return outcomes[0]


def _active_fact(row):
    factual = row["factual"]
    return bool(re.search(r"\b(?:active|open|accepting applications?)\b", factual, re.I)) and not bool(
        re.search(r"\b(?:closed|filled|not active|not open|no longer accepting|not accepting)\b", factual, re.I)
    )


def _polarity(row, positive, negative):
    factual = row["factual"]
    negative_matches = list(negative.finditer(factual))
    has_positive = any(
        not any(match.start() <= positive_match.start() and positive_match.end() <= match.end() for match in negative_matches)
        for positive_match in positive.finditer(factual)
    )
    has_negative = bool(negative_matches)
    if has_positive and has_negative:
        return "CONFLICT"
    if has_negative:
        return "FAIL"
    if has_positive:
        return "PASS"
    return "UNKNOWN"


_INDIA_POSITIVE = re.compile(
    r"\b(?:employer\s+)?(?:explicitly\s+)?(?:supports?|allows?|permits?)\s+(?:employment|hiring|payroll)\s+in\s+india\b|"
    r"\b(?:employer\s+)?(?:hires?|employs?)\s+(?:employees?\s+)?in\s+india\b|"
    r"\bindia\s+(?:employment|hiring|payroll)\s+is\s+(?:supported|available|permitted)\b",
    re.I,
)
_INDIA_NEGATIVE = re.compile(
    r"\b(?:does\s+not|doesn't|cannot|can\s+not|will\s+not|won't|no)\s+(?:hire|employ|support|allow|permit)[^.!?]{0,60}\bin\s+india\b|"
    r"\bindia\s+(?:employment|hiring|payroll)\s+is\s+(?:not\s+supported|unavailable|not\s+available|not\s+permitted|ineligible)\b|"
    r"\bnot\s+eligible\s+for\s+(?:employment|hiring|payroll)\s+in\s+india\b",
    re.I,
)
_PAYROLL_POSITIVE = re.compile(
    r"\b(?:employees?\s+(?:are\s+)?(?:hired|employed)\s+directly|"
    r"direct(?:ly)?[- ](?:employed|hired)|"
    r"direct\s+employer\s+payroll)\b[^.!?]{0,80}\bpermanent\b|"
    r"\bpermanent\b[^.!?]{0,80}\b(?:employees?\s+(?:are\s+)?(?:hired|employed)\s+directly|"
    r"direct(?:ly)?[- ](?:employed|hired)|direct\s+employer\s+payroll)\b",
    re.I,
)
_PAYROLL_NEGATIVE = re.compile(
    r"\b(?:contractor|contract role|third[- ]party|vendor payroll|fixed[- ]term|temporary employment)\b|"
    r"\b(?:not|non[- ])(?:permanent|direct|full[- ]time)\b|"
    r"\b(?:not hired directly|not employed directly|not on employer payroll)\b",
    re.I,
)


def _payroll_fact(row):
    return _polarity(row, _PAYROLL_POSITIVE, _PAYROLL_NEGATIVE)


def _india_fact(row):
    return _polarity(row, _INDIA_POSITIVE, _INDIA_NEGATIVE)


def _location_fact(location_value, work_mode):
    """Require an explicit, unambiguous India scope and approved office locations."""
    raw = " / ".join(str(item) for item in location_value) if isinstance(location_value, (list, tuple)) else str(location_value or "")
    location = re.sub(r"\s+", " ", raw.casefold()).strip()
    has_india = bool(re.search(r"\bindia\b", location))
    has_foreign_country = bool(_FOREIGN_COUNTRY.search(location))
    if work_mode not in {"onsite", "hybrid", "remote"}:
        return "UNKNOWN", "Vacancy work mode is not verified."
    if has_india and has_foreign_country:
        return "UNKNOWN", "Vacancy lists both India and a foreign location; applicability is ambiguous."
    if work_mode == "remote":
        if has_india:
            return "PASS", "Current sourced vacancy is India-remote."
        if has_foreign_country:
            return "FAIL", "Remote vacancy is explicitly outside India."
        return "UNKNOWN", "Remote location does not explicitly establish India-remote eligibility."
    if has_foreign_country and not has_india:
        return "FAIL", "Vacancy location is explicitly outside India."
    if not has_india:
        return "UNKNOWN", "Vacancy location does not establish its country."

    # Accept only named approved locations. Extra location text is unresolved rather
    # than silently inheriting India/eligibility from one approved city.
    office = re.sub(r"\bindia\b|\b(?:onsite|on-site|hybrid)\b|[()\[\]]", " ", location)
    office = office.replace("gurgaon", "gurugram")
    has_approved_office = any(re.search(rf"\b{re.escape(place.replace('gurgaon', 'gurugram'))}\b", office) for place in _ALLOWED_LOCATIONS)
    for place in sorted(_ALLOWED_LOCATIONS, key=len, reverse=True):
        office = re.sub(rf"\b{re.escape(place.replace('gurgaon', 'gurugram'))}\b", " ", office)
    remainder = re.sub(r"[\s,;/|&+-]+", "", office)
    if remainder:
        if not has_approved_office:
            return "FAIL", "Vacancy location is outside the approved India locations."
        return "UNKNOWN", "Vacancy includes an additional or unsupported India location."
    return "PASS", "Current sourced vacancy matches an allowed India location."


def _gate(rows, kind, at, max_age, interpret_fact, missing_reason):
    evidence = _current_evidence(rows, kind, at, max_age)
    interpretations = [(row["state"], interpret_fact(row)) for row in evidence]
    if any(state != interpretation for state, interpretation in interpretations if interpretation in {"PASS", "FAIL"}):
        return {"state": "CONFLICT", "reason": "Stored decision conflicts with its sourced factual evidence.", "evidence": evidence}
    if any(interpretation == "CONFLICT" for _, interpretation in interpretations):
        return {"state": "CONFLICT", "reason": "Current sourced evidence conflicts.", "evidence": evidence}
    if any(interpretation == "UNKNOWN" for _, interpretation in interpretations):
        if any(state == "PASS" for state, _ in interpretations):
            return {"state": "UNKNOWN", "reason": "A recorded PASS has ambiguous factual support.", "evidence": evidence}
        if any(state == "FAIL" for state, _ in interpretations):
            return {"state": "UNKNOWN", "reason": "A recorded FAIL has ambiguous factual support.", "evidence": evidence}
        return {"state": "UNKNOWN", "reason": missing_reason, "evidence": evidence}
    decisions = {interpretation for _, interpretation in interpretations}
    if decisions == {"PASS", "FAIL"}:
        return {"state": "CONFLICT", "reason": "Current sourced evidence conflicts.", "evidence": evidence}
    if decisions == {"FAIL"}:
        return {"state": "FAIL", "reason": "Current sourced evidence confirms this requirement failed.", "evidence": evidence}
    if decisions != {"PASS"}:
        stale = any(row.get("kind") == kind for row in rows)
        reason = "Evidence is stale or lacks a verifiable source." if stale else missing_reason
        return {"state": "UNKNOWN", "reason": reason, "evidence": []}
    return {"state": "PASS", "reason": "Current sourced evidence supports this requirement.", "evidence": evidence}


def _headcount_gate(rows, at, threshold):
    evidence = _current_evidence(rows, "headcount", at, EMPLOYER_EVIDENCE_DAYS)
    if not evidence:
        stale = any(row.get("kind") == "headcount" for row in rows)
        return {
            "state": "UNKNOWN",
            "reason": "Evidence is stale or lacks a verifiable source." if stale else "No current sourced employer-size evidence.",
            "evidence": [],
        }
    interpretations = [(row["state"], _headcount_verdict(row.get("factual"), threshold)) for row in evidence]
    if any(verdict == "UNKNOWN" for _, verdict in interpretations):
        return {"state": "UNKNOWN", "reason": "Sourced headcount does not establish which side of the threshold applies.", "evidence": evidence}
    if any(state != verdict for state, verdict in interpretations):
        return {"state": "CONFLICT", "reason": "Stored headcount decision conflicts with its sourced count.", "evidence": evidence}
    verdicts = {verdict for _, verdict in interpretations}
    if len(verdicts) != 1:
        return {"state": "CONFLICT", "reason": "Current sourced employer-size evidence conflicts.", "evidence": evidence}
    verdict = verdicts.pop()
    return {
        "state": verdict,
        "reason": "Current sourced evidence supports this requirement." if verdict == "PASS" else f"Sourced employer headcount is below the {threshold}-employee threshold.",
        "evidence": evidence,
    }


def assess_hard_eligibility(job, evidence=(), source_references=(), at=None):
    """Assess hard vacancy/employer gates without trusting status flags alone."""
    at = at or datetime.now(timezone.utc)
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    at = at.astimezone(timezone.utc)
    evidence = list(evidence)
    refs = list(source_references)

    gates = {
        "active": _gate(
            evidence,
            "active",
            at,
            VACANCY_EVIDENCE_DAYS,
            lambda row: "PASS" if _active_fact(row) else "FAIL" if re.search(r"\b(?:closed|filled|not active|not open|no longer accepting|not accepting)\b", row["factual"], re.I) else "UNKNOWN",
            "No current sourced vacancy-activity evidence.",
        ),
        "india_employment": _gate(
            evidence,
            "india_eligible",
            at,
            EMPLOYER_EVIDENCE_DAYS,
            _india_fact,
            "No current sourced India-employment eligibility evidence.",
        ),
        "employer_size": _headcount_gate(evidence, at, 500 if job.get("work_mode") == "remote" else 1000),
        "payroll": _gate(
            evidence,
            "direct_permanent_payroll",
            at,
            EMPLOYER_EVIDENCE_DAYS,
            _payroll_fact,
            "No current sourced direct/permanent payroll evidence.",
        ),
    }

    location_value = job.get("location") or ""
    refs_current = any(
        _https_url(ref.get("listing_url") or ref.get("application_url"))
        and (stamp := _timestamp(ref.get("last_seen") or ref.get("imported_at"))) is not None
        and at - timedelta(days=VACANCY_EVIDENCE_DAYS) <= stamp <= at
        for ref in refs
    )
    if not refs_current:
        location_gate = {"state": "UNKNOWN", "reason": "Location has no recent sourced vacancy reference.", "evidence": []}
    else:
        location_state, location_reason = _location_fact(location_value, job.get("work_mode"))
        location_gate = {"state": location_state, "reason": location_reason, "evidence": []}
    gates["location"] = location_gate

    if re.search(r"\bcontract\b|third.party payroll", (job.get("title") or ""), re.I):
        gates["permanent_employment"] = {
            "state": "FAIL",
            "reason": "Role title indicates contract or third-party employment.",
            "evidence": [],
        }
    else:
        gates["permanent_employment"] = {
            "state": gates["payroll"]["state"],
            "reason": gates["payroll"]["reason"],
            "evidence": gates["payroll"]["evidence"],
        }

    states = [gate["state"] for gate in gates.values()]
    state = "FAIL" if "FAIL" in states else "CONFLICT" if "CONFLICT" in states else "UNKNOWN" if "UNKNOWN" in states else "PASS"
    reasons = [f"{name.replace('_', ' ').title()}: {gate['reason']}" for name, gate in gates.items() if gate["state"] != "PASS"]
    if not reasons:
        reasons = ["Current sourced evidence supports every hard eligibility gate."]
    source_url = next(
        (ref.get("listing_url") or ref.get("application_url") for ref in refs if _https_url(ref.get("listing_url") or ref.get("application_url"))),
        job.get("canonical_application_url") or job.get("application_url"),
    )
    return {"state": state, "gates": gates, "reasons": reasons, "source_url": source_url}

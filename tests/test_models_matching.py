import pytest
from pydantic import ValidationError

from job_agent.approvals import package_fingerprint
from job_agent.matching import DeterministicMatcher
from job_agent.models import JobInput, Profile, WorkMode


def test_normalization(record):
    job = JobInput(**(record | {"company": "  Ｅxample  Labs ", "work_mode": " REMOTE ", "skills": [" Python ", "PYTHON", "React"], "application_url": "https://EXAMPLE.com/job/?utm_source=demo&b=2&a=1#section"}))
    assert job.company == "Example Labs"
    assert job.work_mode == WorkMode.REMOTE
    assert job.skills == ["python", "react"]
    assert job.application_url == "https://example.com/job?a=1&b=2"
    assert JobInput(**(record | {"application_url": None})).application_url is None


@pytest.mark.parametrize("url", [42, "javascript:alert(1)", "file:///etc/passwd", "https://user:password@example.com", "https://example.com/?token=secret", "https://example.com:abc/job", "https://example.com/\n", "https://example.com\\evil", "https:///job"])
def test_unsafe_urls(record, url):
    with pytest.raises(ValidationError):
        JobInput(**(record | {"application_url": url}))


@pytest.mark.parametrize("change", [{"company": " "}, {"source_job_id": ""}, {"skills": [""]}, {"skills": [1]}, {"skills": ["x" * 101]}, {"skills": "python"}, {"work_mode": "sometimes"}, {"description": "x" * 20001}, {"min_experience": 6, "max_experience": 2}, {"unknown": "secret"}, {"title": 42}])
def test_invalid_fields(record, change):
    with pytest.raises(ValidationError):
        JobInput(**(record | change))


def test_profile_validation():
    assert Profile(skills=["Python", " PYTHON "]).skills == ["python"]
    for change in [{"target_titles": []}, {"skills": [" "]}, {"locations": ["x" * 151]}, {"experience_years": -1}, {"work_modes": []}]:
        with pytest.raises(ValidationError):
            Profile(**change)


def test_perfect_fit_and_missing(record):
    matcher = DeterministicMatcher()
    profile = Profile(target_titles=["AI Engineer"], skills=["Python"], experience_years=3)
    match = matcher.evaluate(JobInput(**record), profile)
    assert match["score"] == 100
    assert not match["missing_requirements"] and not match["potential_disqualifiers"]
    assert len(match["reasons"]) == 5
    unknown = matcher.evaluate(JobInput(**(record | {"title": "Accountant", "skills": [], "work_mode": "unknown", "min_experience": None, "max_experience": None})), Profile())
    assert unknown["score"] == 15
    assert len(unknown["missing_requirements"]) == 4


def test_partial_skill_and_unknown_experience(record):
    match = DeterministicMatcher().evaluate(JobInput(**(record | {"skills": ["Python", "RAG"]})), Profile())
    assert "Skill: rag" in match["missing_requirements"]
    assert any("unspecified" in reason for reason in match["missing_requirements"])


@pytest.mark.parametrize("years,phrase", [(1, "Below"), (10, "Above")])
def test_disqualifiers(record, years, phrase):
    match = DeterministicMatcher().evaluate(JobInput(**(record | {"location": "USA", "skills": ["RAG"], "work_mode": "onsite", "description": "unpaid"})), Profile(work_modes=[WorkMode.REMOTE], experience_years=years, exclusions=["unpaid"]))
    assert match["score"] == 0
    if years==1:assert len(match["potential_disqualifiers"])==4 and any(phrase in item for item in match["potential_disqualifiers"])
    else:assert len(match["potential_disqualifiers"])==3 and any("exceeds stated range" in item for item in match["missing_requirements"])


def test_fingerprint_changes_for_every_material_field():
    base = dict(job={"id": "1", "version": 1}, resume_hash="a", document_hashes=["b"], answers={"eligible": True}, target="portal", candidate_id="candidate")
    original = package_fingerprint(**base)
    assert original == package_fingerprint(**(base | {"job": {"version": 1, "id": "1"}}))
    for changes in [{"job": {"id": "1", "version": 2}}, {"resume_hash": "c"}, {"document_hashes": ["d"]}, {"answers": {"eligible": False}}, {"target": "other"}, {"candidate_id": "other"}]:
        assert package_fingerprint(**(base | changes)) != original

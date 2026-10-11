import pytest

from job_agent.candidate import SearchBackground
from job_agent.classification import classify, extract_requirements, india_eligibility, rank
from job_agent.models import JobInput, Profile, WorkMode


@pytest.mark.parametrize("title,category,priority", [("GenAI Engineer", "AI_GENAI", "P1"), ("RAG Engineer", "AI_GENAI", "P1"), ("Agentic Engineer II", "AI_GENAI", "P1"), ("Frontend Technical Lead", "FRONTEND_LEADERSHIP", "P1"), ("Frontend Architect", "FRONTEND_LEADERSHIP", "P1"), ("Senior React Developer", "FRONTEND", "P1"), ("UI Technical Lead", "FRONTEND_LEADERSHIP", "P1"), ("Technical Consultant", "CONSULTING", "P2"), ("AI Full Stack Engineer", "FULLSTACK_AI", "P2"), ("Full Stack Engineer", "OTHER", "P2"), ("SQL Data Engineer", "DATA_PYTHON_SQL", "P2"), ("Python Developer", "DATA_PYTHON_SQL", "P2"), ("Backend Lead", "BACKEND", "P3"), ("Account Executive", "OTHER", "P3")])
def test_categories(title, category, priority):
    assert classify(title) == (category, priority)


def test_required_preferred_negation_and_unknown():
    result = extract_requirements("Requirements\nReact and TypeScript\nPython is not required\nPreferred\nLangChain\nRAG is optional\nResponsibilities\nAzure projects")
    assert result["required"] == ["react", "typescript"]
    assert result["preferred"] == ["langchain", "rag"]
    assert "python" not in result["required"] and "azure" not in result["required"]
    unknown = extract_requirements("Use React on our products. No experience required. 3 years experience preferred.")
    assert not unknown["requirements_known"] and unknown["experience"] is None


@pytest.mark.parametrize("location,country,result", [("Bengaluru", None, "ELIGIBLE"), ("India", None, "ELIGIBLE"), ("Remote", "IN", "ELIGIBLE"), ("Remote - USA", None, "INELIGIBLE"), ("Remote", "US", "INELIGIBLE"), ("Worldwide Remote", None, "UNKNOWN"), ("Berlin", None, "UNKNOWN")])
def test_india_eligibility(location, country, result):
    assert india_eligibility(location, WorkMode.REMOTE, country) == result


def test_frontend_lead_and_transition_ai_fit(record):
    frontend = JobInput(**(record | {"title": "Frontend Lead", "description": "Requirements\nReact and TypeScript\n5-8 years of professional experience"}))
    result = rank(frontend, extract_requirements(frontend.description), SearchBackground(), Profile())
    assert result["score"] == 100 and result["seniority_compatibility"] == "COMPATIBLE"
    ai = JobInput(**(record | {"title": "AI Application Engineer", "description": "Requirements\nPython and RAG\n5+ years of software experience"}))
    result = rank(ai, extract_requirements(ai.description), SearchBackground(), Profile())
    assert result["score"] >= 80 and result["backend_penalty"] == 0
    assert any("evidence" in item for item in result["missing_requirements"])


def test_backend_specialization_not_total(record):
    job = JobInput(**(record | {"title": "Backend Lead", "description": "Requirements\nPython and SQL\n5+ years of backend experience"}))
    result = rank(job, extract_requirements(job.description), SearchBackground(), Profile())
    assert result["backend_penalty"] == 15 and result["seniority_compatibility"] == "BELOW_STATED_MINIMUM"
    assert result["score"] < 50


def test_unknown_foreign_mode_and_exclusions(record):
    job = JobInput(**(record | {"title": "AI Engineer", "location": "Global remote", "description": "unpaid", "work_mode": "unknown"}))
    result = rank(job, extract_requirements(job.description), SearchBackground(), Profile(exclusions=["unpaid"]))
    assert result["location_eligibility"] == "UNKNOWN" and result["missing_requirements"]
    assert any("Exclusion" in s for s in result["potential_disqualifiers"])
    job = JobInput(**(record | {"title": "AI Engineer", "location": "USA", "description": "2-4 years of experience", "work_mode": "onsite"}))
    result = rank(job, extract_requirements(job.description), SearchBackground(), Profile(work_modes=[WorkMode.REMOTE]))
    assert result["location_eligibility"] == "INELIGIBLE" and result["seniority_compatibility"] == "REVIEW_REQUIRED"


def test_missing_required_skill_evidence(record):
    job = JobInput(**record)
    result = rank(job, {"required": ["python"], "preferred": [], "mentioned": ["python"], "experience": None, "requirements_known": True}, SearchBackground(developing_skills=[]), Profile())
    assert "Required skill: python" in result["missing_requirements"]


def test_background_bounds_and_normalization():
    assert SearchBackground(established_skills=[" React ", "REACT"]).established_skills == ["react"]
    with pytest.raises(ValueError):
        SearchBackground(total_years=2, backend_years=3)


def test_non_engineering_ai_title_and_junior_scope(record):
    assert classify("Agentic Product Manager") == ("OTHER", "P3")
    job = JobInput(**(record | {"title": "SDE I - Frontend", "description": "Requirements\nReact and TypeScript required\n3+ years of professional experience"}))
    result = rank(job, extract_requirements(job.description), SearchBackground(), Profile())
    assert result["priority"] == "P2" and result["score"] < 90
    assert result["seniority_compatibility"] == "REVIEW_REQUIRED"

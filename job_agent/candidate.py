"""Search preferences from user-provided background; not generated resume claims."""
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .models import Profile, StrictModel


class SearchBackground(StrictModel):
    total_years: float = Field(default=7, ge=0, le=60)
    backend_years: float = Field(default=3.5, ge=0, le=60)
    established_skills: list[str] = Field(default_factory=lambda: ["angular", "react", "javascript", "typescript", "html", "css", "rest apis", "enterprise applications", "sap spartacus", "sap commerce frontend integration"], max_length=100)
    developing_skills: list[str] = Field(default_factory=lambda: [".net", "c#", "python", "sql", "data science", "machine learning", "llm application engineering", "rag", "langchain", "langgraph", "fastapi", "azure"], max_length=100)
    evidence_note: str = Field(default="User-reported strengths and additional experience/learning; individual academic/project/professional evidence remains unspecified.", max_length=1000)

    @field_validator("established_skills", "developing_skills")
    @classmethod
    def normalize_skills(cls, values):
        return Profile.normalized_list(values)

    @model_validator(mode="after")
    def experience_bounds(self):
        if self.backend_years > self.total_years:
            raise ValueError("backend_years_exceed_total")
        return self


class CandidateProfile(StrictModel):
    """Reviewed matching evidence; categories avoid turning projects into employment."""
    version: int = Field(default=1, ge=1)
    target_roles: dict[str, int] = Field(default_factory=lambda: {
        "frontend": 5, "ai_application": 5, "genai_application": 5,
        "frontend_lead": 4, "fullstack_ai": 4,
    })
    employment_skills: list[str] = Field(default_factory=lambda: ["angular", "react", "javascript", "typescript", "rest apis", ".net", "sql"])
    project_skills: list[str] = Field(default_factory=lambda: ["python", "fastapi", "rag", "faiss", "embeddings", "ollama", "automation"])
    learning_skills: list[str] = Field(default_factory=list)
    total_experience_years: float | None = Field(default=7, ge=0, le=60)
    ai_employment_years: float | None = Field(default=None, ge=0, le=60)
    seniority: list[str] = Field(default_factory=lambda: ["senior", "lead"])
    preferred_locations: list[str] = Field(default_factory=lambda: ["noida", "greater noida", "delhi ncr", "gurugram", "gurgaon", "mohali", "chandigarh", "remote india"])
    exclusions: list[str] = Field(default_factory=lambda: ["unpaid", "commission only"])
    reviewed: bool = False

    @field_validator("employment_skills", "project_skills", "learning_skills", "seniority", "preferred_locations", "exclusions")
    @classmethod
    def normalize_lists(cls, values):
        return Profile.normalized_list(values)

    @field_validator("target_roles")
    @classmethod
    def role_weights(cls, value):
        allowed = {"frontend", "ai_application", "genai_application", "frontend_lead", "fullstack_ai"}
        if not value or set(value) - allowed or any(not isinstance(v, int) or not 1 <= v <= 5 for v in value.values()):
            raise ValueError("invalid_role_priorities")
        return value

    @model_validator(mode="after")
    def truthful_ai_experience(self):
        if self.ai_employment_years is not None and self.ai_employment_years > (self.total_experience_years or 0):
            raise ValueError("ai_experience_exceeds_total")
        return self


class ResumeReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reviewed: bool = False

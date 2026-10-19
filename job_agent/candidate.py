"""Search preferences from user-provided background; not generated resume claims."""
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .models import Profile, StrictModel


class SearchBackground(StrictModel):
    total_years: float = Field(default=0, ge=0, le=60)
    backend_years: float = Field(default=0, ge=0, le=60)
    established_skills: list[str] = Field(default_factory=list, max_length=100)
    developing_skills: list[str] = Field(default_factory=list, max_length=100)
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
    """One effective profile with scoped professional evidence and provenance."""
    version: int = Field(default=1, ge=1)
    target_roles: dict[str, int] = Field(default_factory=lambda: {
        "frontend": 5, "ai_application": 5, "genai_application": 5,
        "frontend_lead": 4, "fullstack_ai": 4,
    })
    target_titles: list[str] = Field(default_factory=lambda: ["senior frontend/ui engineer","angular/react/next.js developer","frontend technical lead","frontend solutions lead","frontend architect","ai frontend engineer","genai/ai/applied ai engineer","llm application/integration engineer","rag engineer","ai automation engineer","ai/genai solutions consultant","frontend-heavy full-stack ai/python/.net"],max_length=30)
    search_skills: list[str] = Field(default_factory=list,max_length=100)
    employment_skills: list[str] = Field(default_factory=list)
    project_skills: list[str] = Field(default_factory=list)
    learning_skills: list[str] = Field(default_factory=list)
    professional_skills: list[str] = Field(default_factory=list,max_length=150)
    total_experience_years: float | None = Field(default=None, ge=0, le=60)
    ai_employment_years: float | None = Field(default=None, ge=0, le=60)
    seniority: list[str] = Field(default_factory=lambda: ["senior", "lead"])
    preferred_locations: list[str] = Field(default_factory=lambda: ["India"])
    exclusions: list[str] = Field(default_factory=lambda: ["unpaid", "commission only"])
    reviewed: bool = False
    technology_years: dict[str,float] = Field(default_factory=dict)
    confirmed_facts: dict[str,str] = Field(default_factory=dict)
    backend_experience_years: float = Field(default=0,ge=0,le=60)
    background_established_skills: list[str] = Field(default_factory=list,max_length=100)
    background_developing_skills: list[str] = Field(default_factory=list,max_length=100)
    candidate_name: str = ""
    home_location: str = ""
    professional_ai_confirmed: bool = False
    professional_ai_summary: list[str] = Field(default_factory=list,max_length=20)
    skill_evidence: dict[str,list[dict[str,str]]] = Field(default_factory=dict)
    fact_provenance: dict[str,list[dict[str,str]]] = Field(default_factory=dict)
    education: list[str] = Field(default_factory=list,max_length=20)
    approved_application_answers: dict[str,str] = Field(default_factory=dict)
    document_versions: dict[str,str] = Field(default_factory=dict)

    @field_validator("employment_skills", "project_skills", "learning_skills", "professional_skills", "seniority", "preferred_locations", "exclusions", "target_titles", "search_skills", "background_established_skills", "background_developing_skills")
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
        if self.total_experience_years is not None and self.backend_experience_years>self.total_experience_years:raise ValueError("backend_years_exceed_total")
        return self

    @field_validator("technology_years")
    @classmethod
    def valid_technology_years(cls,value):
        if any(not name.strip() or years<0 or years>60 for name,years in value.items()):raise ValueError("invalid_technology_years")
        return {name.strip().casefold():years for name,years in value.items()}

    def search_profile(self)->Profile:
        skills=sorted(set(self.search_skills+self.professional_skills+self.employment_skills+self.project_skills+self.learning_skills))
        return Profile(target_titles=self.target_titles,skills=skills,locations=self.preferred_locations,work_modes=["remote","hybrid","onsite"],experience_years=self.total_experience_years,exclusions=self.exclusions)

    def search_background(self)->SearchBackground:
        established=self.background_established_skills or sorted(set(self.professional_skills+self.employment_skills+self.project_skills))
        developing=self.background_developing_skills or self.learning_skills
        return SearchBackground(total_years=self.total_experience_years or 0,backend_years=self.backend_experience_years,established_skills=established,developing_skills=developing,evidence_note="Versioned user-confirmed search evidence; technology duration does not imply employer or production tenure.")

SKILL_DISPLAY={
    ".net core":".NET Core","javascript":"JavaScript","typescript":"TypeScript","python":"Python","fastapi":"FastAPI","faiss":"FAISS","rag":"RAG","sql":"SQL","sqlite":"SQLite","llm":"LLM","llm application engineering":"LLM application engineering","llm inference/integration":"LLM inference/integration","html5":"HTML5","css3":"CSS3","rxjs":"RxJS","next.js":"Next.js","pydantic":"Pydantic","websockets":"WebSockets","rest apis":"REST APIs","sql server":"SQL Server","hugging face":"Hugging Face","ollama":"Ollama","pytest":"pytest","playwright":"Playwright","github":"GitHub","git/github":"Git/GitHub","github copilot agent":"GitHub Copilot Agent","mcp-assisted sdd":"MCP-assisted SDD","azure":"Azure","azure fundamentals":"Azure fundamentals","langchain text splitting":"LangChain text splitting","ui architecture":"UI Architecture"
}

SKILL_DOMAINS={
    "Frontend and Architecture":("angular","react","next.js","javascript","typescript","rxjs","html5","css3","rest apis","websockets","reusable components","ui architecture","performance optimisation"),
    "AI Application Engineering":("rag","llm inference/integration","vector search","faiss","embeddings","hugging face","ollama","langchain text splitting","prompt engineering","grounding","structured outputs","hybrid ranking"),
    "Backend and Data":("python","fastapi","pydantic","sql","sqlite",".net core","sql server"),
    "Quality, Delivery and Leadership":("testing","mentoring","client-facing delivery","pytest","playwright","git/github","github copilot agent","mcp-assisted sdd","azure fundamentals"),
}

def display_skill(value:str)->str:
    normalized=value.strip().casefold()
    return SKILL_DISPLAY.get(normalized,normalized.title())


class ResumeReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reviewed: bool = False

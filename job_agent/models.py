"""Validated public input; never interpret imported text as instructions."""
import re
import unicodedata
from enum import StrEnum
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def clean(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def key(value: str) -> str:
    return clean(value).casefold()


class Status(StrEnum):
    NEW = "NEW"
    SHORTLISTED = "SHORTLISTED"
    NOT_RELEVANT = "NOT_RELEVANT"
    PREPARING = "PREPARING"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    APPROVED = "APPROVED"
    SUBMITTED = "SUBMITTED"
    INTERVIEW = "INTERVIEW"
    REJECTED = "REJECTED"
    OFFER = "OFFER"


class WorkMode(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNKNOWN = "unknown"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, validate_default=True)


class JobInput(StrictModel):
    source: str = Field(min_length=1, max_length=100)
    source_job_id: str | None = Field(default=None, min_length=1, max_length=200)
    company: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=200)
    location: str = Field(min_length=1, max_length=200)
    work_mode: WorkMode = WorkMode.UNKNOWN
    description: str = Field(default="", max_length=20000)
    skills: list[str] = Field(default_factory=list, max_length=100)
    application_url: str | None = Field(default=None, max_length=2000)
    min_experience: float | None = Field(default=None, ge=0, le=60)
    max_experience: float | None = Field(default=None, ge=0, le=60)
    is_sample: bool = False

    @field_validator("source", "source_job_id", "company", "title", "location", mode="before")
    @classmethod
    def normalize_text(cls, value):
        return clean(value) if isinstance(value, str) else value

    @field_validator("work_mode", mode="before")
    @classmethod
    def normalize_mode(cls, value):
        return key(value) if isinstance(value, str) else value

    @field_validator("skills", mode="before")
    @classmethod
    def normalize_skills(cls, value):
        if isinstance(value, list):
            if any(not isinstance(s, str) or not clean(s) or len(s) > 100 for s in value):
                raise ValueError("invalid skill")
            return sorted(set(key(s) for s in value))
        return value

    @field_validator("application_url", mode="before")
    @classmethod
    def safe_url(cls, value):
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("URL must be text")
        if re.search(r"[\x00-\x20\\]", value):
            raise ValueError("unsafe URL")
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
            raise ValueError("HTTP(S) URL without credentials required")
        # Access the port to validate malformed ports before persistence.
        parts.port
        query = parse_qsl(parts.query, keep_blank_values=True)
        if any(re.search(r"token|secret|password|cookie|credential|api.?key", k, re.I) for k, _ in query):
            raise ValueError("sensitive URL query")
        query = [(k, v) for k, v in query if not k.lower().startswith("utm_")]
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), urlencode(sorted(query)), ""))

    @model_validator(mode="after")
    def experience_range(self):
        if self.min_experience is not None and self.max_experience is not None and self.min_experience > self.max_experience:
            raise ValueError("invalid experience range")
        return self


class Profile(StrictModel):
    target_titles: list[str] = Field(default_factory=lambda: ["GenAI Engineer", "AI Engineer", "AI Application Engineer", "Applied AI Engineer", "AI-focused Software Engineer"], min_length=1, max_length=30)
    skills: list[str] = Field(default_factory=lambda: ["Angular", "React", "JavaScript", "TypeScript", ".NET", "REST APIs", "Python", "Data Science", "ML fundamentals"], max_length=100)
    locations: list[str] = Field(default_factory=lambda: ["India"], min_length=1, max_length=30)
    work_modes: list[WorkMode] = Field(default_factory=lambda: [WorkMode.REMOTE, WorkMode.HYBRID, WorkMode.ONSITE], min_length=1, max_length=4)
    experience_years: float | None = Field(default=None, ge=0, le=60)
    exclusions: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("target_titles", "skills", "locations", "exclusions")
    @classmethod
    def normalized_list(cls, values):
        if any(not clean(v) or len(v) > 150 for v in values):
            raise ValueError("invalid preference")
        return sorted(set(key(v) for v in values))


class StatusChange(StrictModel):
    status: Status

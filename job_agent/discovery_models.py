"""Discovery configuration; endpoints are derived, never user-supplied URLs."""
from enum import StrEnum

from pydantic import Field, model_validator

from .models import StrictModel


class Category(StrEnum):
    AI_GENAI = "AI_GENAI"
    FRONTEND = "FRONTEND"
    FRONTEND_LEADERSHIP = "FRONTEND_LEADERSHIP"
    CONSULTING = "CONSULTING"
    FULLSTACK_AI = "FULLSTACK_AI"
    DATA_PYTHON_SQL = "DATA_PYTHON_SQL"
    BACKEND = "BACKEND"
    OTHER = "OTHER"


class SourceConfig(StrictModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,59}$")
    provider: str = Field(pattern=r"^(greenhouse|lever|remoteok|wwr|smartrecruiters|amazon)$")
    company: str = Field(min_length=1, max_length=200)
    board: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$")
    region: str = Field(default="global", pattern=r"^(global|eu)$")
    enabled: bool = False
    career_url: str | None = Field(default=None, max_length=1000)
    verified: bool = False
    verified_at: str | None = None
    verification_evidence: str | None = Field(default=None, max_length=1000)
    india_relevant: bool | None = None
    cooldown_seconds: int | None = Field(default=None, ge=0, le=604800)

    @model_validator(mode="after")
    def supported_region(self):
        if self.provider in {"greenhouse", "remoteok", "wwr"} and self.region != "global":
            raise ValueError("unsupported_greenhouse_region")
        return self


class SourceToggle(StrictModel):
    enabled: bool


class DiscoverySettings(StrictModel):
    timeout_seconds: float = Field(default=10, ge=0.1, le=30)
    retry_limit: int = Field(default=2, ge=0, le=2)
    cooldown_seconds: int = Field(default=3600, ge=0, le=86400)
    concurrency_limit: int = Field(default=4, ge=1, le=8)
    max_requests: int = Field(default=20, ge=1, le=100)
    max_runtime_seconds: int = Field(default=120, ge=1, le=600)
    max_response_bytes: int = Field(default=8 * 1024 * 1024, ge=1024, le=16 * 1024 * 1024)
    page_size: int = Field(default=100, ge=1, le=100)
    max_records: int = Field(default=5000, ge=1, le=10000)


class DiscoveryConfig(StrictModel):
    settings: DiscoverySettings = Field(default_factory=DiscoverySettings)
    sources: list[SourceConfig] = Field(default_factory=list, max_length=100)


COUNTERS = ("requests", "http_errors", "response_bytes", "records_fetched", "new_jobs", "updated_jobs", "unchanged_jobs", "duplicates", "rejected_records", "retries", "failed_sources", "skipped_sources")


def metrics() -> dict:
    return dict.fromkeys(COUNTERS, 0)

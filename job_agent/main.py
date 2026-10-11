"""Local HTTP boundary with origin/host defenses and safe validation errors."""
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .connectors import FileConnector, ImportProblem, MAX_BYTES
from .database import Database
from .models import Profile, Status, StatusChange, WorkMode
from .candidate import CandidateProfile
from .service import JobService
from .candidate import SearchBackground
from .discovery import Discovery, RunBusy
from .discovery_models import Category, DiscoveryConfig, SourceConfig, SourceToggle
from .registry import Registry, load_config

STATIC = Path(__file__).parent / "static"


def create_app(db_path: str | Path = "data/jobs.sqlite3", discovery_config: DiscoveryConfig | None = None, discovery_client_factory=None) -> FastAPI:
    service = JobService(Database(db_path))
    config_path = Path("config/discovery.json")
    config = discovery_config or (load_config(config_path) if config_path.exists() else DiscoveryConfig())
    discovery = Discovery(service.db, config.settings, discovery_client_factory)
    registry = discovery.registry
    registry.seed(config)

    @asynccontextmanager
    async def lifespan(app):
        yield
        discovery.close()

    app = FastAPI(title="Local Job Agent", version="0.2.0", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.service = service
    app.state.discovery = discovery
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            fetch_site = request.headers.get("sec-fetch-site")
            if fetch_site == "cross-site" or (origin and origin != str(request.base_url).rstrip("/")):
                return JSONResponse({"detail": "untrusted_origin"}, status_code=403)
            try:
                length = int(request.headers.get("content-length", "0"))
            except ValueError:
                return JSONResponse({"detail": "invalid_content_length"}, status_code=400)
            if length > MAX_BYTES + 65536:
                service.db.record_error("request_too_large")
                return JSONResponse({"detail": "request_too_large"}, status_code=413)
            # Cap actual request body even when Content-Length is absent/incorrect.
            body = bytearray()
            async for chunk in request.stream():
                if len(body) + len(chunk) > MAX_BYTES + 65536:
                    service.db.record_error("request_too_large")
                    return JSONResponse({"detail": "request_too_large"}, status_code=413)
                body.extend(chunk)
            request._body = bytes(body)
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        service.db.record_error("request_validation_failed")
        return JSONResponse({"detail": "request_validation_failed"}, status_code=422)

    @app.exception_handler(sqlite3.Error)
    async def database_error(request, exc):
        # Database may be unavailable; do not leak SQL/path or recurse into audit.
        return JSONResponse({"detail": "database_unavailable"}, status_code=503)

    @app.get("/", include_in_schema=False)
    def dashboard():
        return FileResponse(STATIC / "index.html")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return Response(status_code=204)

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/api/health")
    def health():
        return {"status": "ok", "scope": "local_manual_tracking", "submission_enabled": False}

    @app.get("/api/statuses")
    def statuses():
        return [s.value for s in Status]

    @app.get("/api/jobs")
    def jobs(q: str = Query(default="", max_length=200), status: Status | None = None, work_mode: WorkMode | None = None, min_score: int = Query(default=0, ge=0, le=100), category: Category | None = None, priority: Literal["P1", "P2", "P3"] | None = None, source: str | None = Query(default=None, max_length=60), sort: Literal["score_desc", "score_asc", "last_seen", "freshness","newest","priority","updated"] = "score_desc", kind: Literal["LIVE", "SAMPLE", "IMPORTED"] | None = None, eligibility: Literal["ELIGIBLE","INELIGIBLE","UNKNOWN"] | None = None, seniority: Literal["JUNIOR","MID_LEVEL","SENIOR","LEAD","STAFF","PRINCIPAL","ARCHITECT","MANAGER","UNKNOWN"] | None = None, employer: str | None = Query(default=None,max_length=200), activity: Literal["ACTIVE","POSSIBLY_CLOSED","CLOSED","UNKNOWN"] | None = None, page: int | None=Query(default=None,ge=1), page_size:int=Query(default=50,ge=10,le=100), freshness:Literal["1h","6h","12h","24h","48h","7d","unknown"]|None=None, location_bucket:str|None=Query(default=None,max_length=200), experience:Literal["0-3","3-5","5-8","7-10","10+","unknown"]|None=None, skills:str|None=Query(default=None,max_length=500), skill_mode:Literal["any","all"]="any", title:str|None=Query(default=None,max_length=200), platform:str|None=Query(default=None,max_length=30)):
        return service.list_jobs(q,status,work_mode,min_score,category,priority,source,sort,kind,eligibility,seniority,employer,activity,page,page_size,freshness,location_bucket,experience,skills,skill_mode,title,platform)

    @app.get("/api/overview")
    def overview(): return service.overview()

    @app.get("/api/jobs/{job_id}")
    def job_detail(job_id: str):
        job = service.get_job(job_id)
        if job is None:
            raise HTTPException(404, "job_not_found")
        return job

    @app.patch("/api/jobs/{job_id}/status")
    def change_status(job_id: str, change: StatusChange):
        if not service.set_status(job_id, change.status):
            raise HTTPException(404, "job_not_found")
        return service.get_job(job_id)

    @app.get("/api/profile")
    def profile():
        return service.get_profile()

    @app.put("/api/profile")
    def update_profile(profile: Profile):
        return service.save_profile(profile)

    @app.get("/api/candidate-profile")
    def candidate_profile(): return service.get_candidate_profile()

    @app.put("/api/candidate-profile")
    def update_candidate_profile(profile: CandidateProfile): return service.save_candidate_profile(profile)

    @app.post("/api/candidate-profile/resume")
    async def attach_resume(file: UploadFile = File(...)):
        extension=Path(file.filename or "").suffix.lower().lstrip(".")
        payload=await file.read(5*1024*1024+1)
        await file.close()
        try:return service.attach_resume(payload,extension)
        except ValueError:raise HTTPException(422,"invalid_resume") from None

    @app.post("/api/recommendations/refresh")
    def refresh_recommendations(top_k:int=Query(default=250,ge=1,le=1000),strategy:Literal["whole","section"]="section"):
        return service.refresh_recommendations(top_k,strategy)

    @app.get("/api/recommendations")
    def recommendations(eligibility:Literal["ELIGIBLE","UNKNOWN"]|None=None,role_family:Category|None=None,limit:int=Query(default=50,ge=1,le=100)):
        return service.list_recommendations(eligibility,role_family,limit)

    @app.get("/api/audit")
    def audit(limit: int = Query(default=30, ge=1, le=100)):
        return service.audit_events(limit)

    @app.get("/api/sources")
    def sources():
        return registry.list()

    @app.post("/api/sources")
    def add_source(source: SourceConfig):
        try:
            registry.sync(DiscoveryConfig(sources=[source]))
        except (ValueError, sqlite3.IntegrityError):
            raise HTTPException(409, "source_configuration_conflict") from None
        return registry.list()

    @app.patch("/api/sources/{source_id}")
    def toggle_source(source_id: str, toggle: SourceToggle):
        if not registry.toggle(source_id, toggle.enabled):
            raise HTTPException(404, "source_not_found")
        return {"id": source_id, "enabled": toggle.enabled}

    @app.post("/api/discovery/runs", status_code=202)
    def start_discovery():
        try:
            return {"run_id": discovery.start()}
        except RunBusy:
            raise HTTPException(409, "discovery_in_progress") from None

    @app.get("/api/discovery/latest")
    def latest_discovery():
        return discovery.latest()

    @app.get("/api/discovery/runs/{run_id}")
    def get_discovery(run_id: str):
        run = discovery.get_run(run_id)
        if run is None:
            raise HTTPException(404, "run_not_found")
        return run

    @app.get("/api/search-background")
    def search_background():
        return registry.background().model_dump()

    @app.put("/api/search-background")
    def update_background(background: SearchBackground):
        return service.save_background(background)

    @app.post("/api/import")
    async def import_jobs(file: UploadFile = File(...)):
        try:
            extension = Path(file.filename or "").suffix.lower().lstrip(".")
            if extension not in {"json", "csv"}:
                raise ImportProblem("unsupported_format")
            payload = await file.read(MAX_BYTES + 1)
            rows = FileConnector().read(payload, extension)
            return service.import_rows(rows)
        except ImportProblem as error:
            service.db.record_error(error.code)
            raise HTTPException(413 if error.code == "file_too_large" else 422, error.code) from None
        finally:
            await file.close()

    return app

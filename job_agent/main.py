"""Local HTTP boundary with origin/host defenses and safe validation errors."""
import sqlite3
import json
import hashlib
import os
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
from .resume_review import FactDecision
from .service import JobService
from .candidate import SearchBackground
from .discovery import Discovery, RunBusy
from .discovery_models import Category, DiscoveryConfig, SourceConfig, SourceToggle
from .registry import Registry, load_config
from .m2d import GmailExportAdapter,M2DEngine
from .m2d_models import EmailExportMessage
from .jobqueue import JobQueueWorkbook
from .m3 import M3Engine
from .m3_export import M3Workbook
from .m3_models import ContactInput,DraftRequest,DraftResolution,EmployerQuestion,PacketEdit
from .gmail_local import GmailDraftAdapter
from pydantic import BaseModel,Field

STATIC = Path(__file__).parent / "static"


def create_app(db_path: str | Path = "data/jobs.sqlite3", discovery_config: DiscoveryConfig | None = None, discovery_client_factory=None) -> FastAPI:
    service = JobService(Database(db_path))
    config_path = Path("config/discovery.json")
    config = discovery_config or (load_config(config_path) if config_path.exists() else DiscoveryConfig())
    discovery = Discovery(service.db, config.settings, discovery_client_factory)
    registry = discovery.registry
    registry.seed(config)
    m2d=M2DEngine(service.db);m2d.seed();m2d.sync_existing_jobs()
    m3=M3Engine(service.db)
    from .browser_store import BrowserStore
    browser_store=BrowserStore(service.db)

    @asynccontextmanager
    async def lifespan(app):
        yield
        discovery.close()

    app = FastAPI(title="Local Job Agent", version="0.2.0", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.service = service
    app.state.discovery = discovery
    app.state.m2d = m2d
    app.state.m3 = m3
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

    # Captured once at startup: do not confuse on-disk edits with loaded runtime.
    from .requirement_clauses import VERSION as requirement_version
    source_root=Path(__file__).resolve().parent
    source_hash=hashlib.sha256()
    for source_file in sorted(source_root.rglob('*')):
        if source_file.is_file() and source_file.suffix in {'.py','.js','.html','.css'}:
            source_hash.update(source_file.relative_to(source_root).as_posix().encode()+b'\0'+source_file.read_bytes()+b'\0')
    with service.db.transaction() as conn:schema=conn.execute('PRAGMA user_version').fetchone()[0]
    runtime_identity={'pid':os.getpid(),'source_root':str(source_root),'source_sha256':source_hash.hexdigest(),'requirements_version':requirement_version,'database_path':str(service.db.path.resolve()),'schema_version':schema,'r2_version':'profile-gmail-1','live_draft_creation':False}

    @app.get("/api/health")
    def health():
        return {"status": "ok", "scope": "local_manual_tracking", "submission_enabled": False,'runtime':runtime_identity}

    @app.get("/api/statuses")
    def statuses():
        return [s.value for s in Status]

    @app.get("/api/jobs")
    def jobs(q: str = Query(default="", max_length=200), status: Status | None = None, work_mode: WorkMode | None = None, min_score: int = Query(default=0, ge=0, le=100), category: Category | None = None, priority: Literal["P1", "P2", "P3"] | None = None, source: str | None = Query(default=None, max_length=60), sort: Literal["score_desc", "score_asc", "last_seen", "freshness","newest","priority","updated"] = "score_desc", kind: Literal["LIVE", "SAMPLE", "IMPORTED", "EMAIL"] | None = None, eligibility: Literal["ELIGIBLE","INELIGIBLE","UNKNOWN"] | None = None, seniority: Literal["JUNIOR","MID_LEVEL","SENIOR","LEAD","STAFF","PRINCIPAL","ARCHITECT","MANAGER","UNKNOWN"] | None = None, employer: str | None = Query(default=None,max_length=200), activity: Literal["ACTIVE","POSSIBLY_CLOSED","CLOSED","UNKNOWN"] | None = None, page: int | None=Query(default=None,ge=1), page_size:int=Query(default=50,ge=10,le=100), freshness:Literal["1h","6h","12h","24h","48h","7d","unknown"]|None=None, location_bucket:str|None=Query(default=None,max_length=200), experience:Literal["0-3","3-5","5-8","7-10","10+","unknown"]|None=None, skills:str|None=Query(default=None,max_length=500), skill_mode:Literal["any","all"]="any", title:str|None=Query(default=None,max_length=200), platform:str|None=Query(default=None,max_length=30)):
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

    @app.post('/api/jobs/{job_id}/review-dismissal')
    def dismiss_review(job_id:str):
        from .database import now
        from .runtime_policy import digest
        with service.db.transaction() as conn:
            row=conn.execute('SELECT id FROM jobs WHERE id=?',(job_id,)).fetchone()
            if not row:raise HTTPException(404,'job_not_found')
            state=conn.execute('SELECT job_key FROM job_operational_state WHERE job_id=?',(job_id,)).fetchone()
            key=state[0] if state else 'job:'+job_id
            identifier=digest([key,'user_reported_unavailable'])
            conn.execute('INSERT OR IGNORE INTO job_evidence VALUES(?,?,?,?,?,?,?,?,?,?)',(identifier,key,'review_queue_dismissal','USER_REPORTED_UNAVAILABLE','User reported application link unavailable',None,None,now(),None,identifier))
            service.db.audit(conn,'REVIEW_JOB_DISMISSED',{'reason':'user_reported_unavailable','submission_verified':False},job_id)
        return {'removed_from_review':True,'history_preserved':True}

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

    @app.post("/api/candidate-profile/resume/parse")
    def parse_resume():
        try:return service.parse_resume()
        except ValueError as error:raise HTTPException(422,str(error)) from None

    @app.get("/api/candidate-profile/facts")
    def proposed_facts():return service.proposed_facts()

    @app.patch("/api/candidate-profile/facts/{proposal_id}")
    def review_fact(proposal_id:str,decision:FactDecision):
        try:reviewed=service.review_fact(proposal_id,decision)
        except ValueError as error:raise HTTPException(422,str(error)) from None
        if not reviewed:raise HTTPException(404,"proposal_not_found")
        return {"status":decision.action}

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

    @app.get('/api/inbox/messages')
    def retained_inbox():
        from .command_center import inbox
        return inbox(service.db)

    @app.get('/api/activity/runs')
    def retained_runs():
        from .command_center import runs
        return runs(service.db)

    @app.get('/api/notifications')
    def notification_center():
        from .orchestration import notifications
        return notifications(service.db)

    class NotificationDecision(BaseModel):
        revision:int=Field(ge=1)
        snooze_minutes:int=Field(default=0,ge=0,le=1440)

    @app.post('/api/notifications/{identifier}/acknowledge')
    def notification_ack(identifier:str,data:NotificationDecision):
        from .orchestration import acknowledge
        try:acknowledge(service.db,identifier,data.revision,data.snooze_minutes)
        except ValueError as error:raise HTTPException(409,str(error)) from None
        return {'saved':True}

    class NotificationPreferences(BaseModel):
        sound:bool=False
        desktop:bool=False
        quiet_start:int=Field(default=22,ge=0,le=23)
        quiet_end:int=Field(default=8,ge=0,le=23)

    @app.put('/api/notifications/preferences')
    def notification_preferences(data:NotificationPreferences):
        with service.db.transaction() as c:c.execute('UPDATE notification_preferences SET sound=?,desktop=?,quiet_start=?,quiet_end=? WHERE id=1',(data.sound,data.desktop,data.quiet_start,data.quiet_end))
        return {'saved':True,'runtime_audio':'requires_open_page_and_user_gesture','desktop_permission':'browser_controlled'}

    @app.get('/api/orchestration/plans')
    def application_plans():
        from .orchestration import plans
        return plans(service.db)

    @app.post('/api/orchestration/plans')
    def create_application_plans():
        from .orchestration import plan_batches
        return plan_batches(service.db)

    @app.post('/api/orchestration/plans/{identifier}/prepare')
    def prepare_application_plan(identifier:str):
        with service.db.transaction() as c:row=c.execute("SELECT id FROM application_plans WHERE id=? AND state='PLANNED'",(identifier,)).fetchone()
        if not row:raise HTTPException(409,'plan_not_pending')
        result=browser_batch(BrowserBatchInput(limit=5))
        with service.db.transaction() as c:c.execute('UPDATE application_plans SET state=? WHERE id=?',('RELEASED:'+result['batch_id'],identifier))
        return result

    @app.get('/api/orchestration/schedules')
    def schedule_plans():
        from .orchestration import schedules
        return schedules(service.db)

    class SchedulePlan(BaseModel):
        stage:Literal['DISCOVERY','GMAIL_INTAKE','VERIFICATION','PREPARATION','NOTIFICATIONS']
        interval_seconds:int=Field(ge=60,le=604800)
        next_run:str=Field(max_length=40)

    @app.post('/api/orchestration/schedules')
    def create_schedule_plan(data:SchedulePlan):
        from .orchestration import schedule_plan
        try:identifier=schedule_plan(service.db,data.stage,data.interval_seconds,data.next_run)
        except ValueError as error:raise HTTPException(422,str(error)) from None
        return {'id':identifier,'enabled':False,'requires_separate_activation_approval':True}

    @app.get('/api/browser/batches/{identifier}/questions')
    def consolidated_questions(identifier:str):
        from .orchestration import batch_questions
        return {'items':batch_questions(service.db,identifier)}

    class BatchAnswer(BaseModel):
        id:str=Field(min_length=64,max_length=64)
        value:str=Field(min_length=1,max_length=10000)
    class BatchAnswers(BaseModel):
        answers:list[BatchAnswer]=Field(min_length=1,max_length=100)

    @app.post('/api/browser/batches/{identifier}/answers')
    def consolidated_answers(identifier:str,data:BatchAnswers):
        from .orchestration import save_batch_answers,queue_resume,dispatch_pending_resumes
        try:
            result=save_batch_answers(service.db,identifier,[a.model_dump() for a in data.answers])
            queue_resume(service.db,result['affected_applications'])
            result['worker_pid']=dispatch_pending_resumes(service.db)
            result['resume_state']='STARTED' if result['worker_pid'] else 'QUEUED_AFTER_ACTIVE_WORK'
            return result
        except ValueError as error:raise HTTPException(422,str(error)) from None

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
            m2d.plan_week()
            return {"run_id": discovery.start()}
        except RunBusy:
            raise HTTPException(409, "discovery_in_progress") from None

    @app.get("/api/discovery/latest")
    def latest_discovery():
        run=discovery.latest();snapshot=m2d.reconcile_discovery_run(run)
        if snapshot:m2d.sync_existing_jobs()
        return run

    @app.get("/api/discovery/runs/{run_id}")
    def get_discovery(run_id: str):
        run = discovery.get_run(run_id)
        if run is None:
            raise HTTPException(404, "run_not_found")
        snapshot=m2d.reconcile_discovery_run(run)
        if snapshot:m2d.sync_existing_jobs()
        return run

    @app.get("/api/search-background")
    def search_background():
        return service.get_background()

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
            report=service.import_rows(rows);m2d.sync_existing_jobs();return report
        except ImportProblem as error:
            service.db.record_error(error.code)
            raise HTTPException(413 if error.code == "file_too_large" else 422, error.code) from None
        finally:
            await file.close()

    @app.get("/api/m2d/summary")
    def m2d_summary():
        raw=service.get_candidate_profile();candidate=CandidateProfile.model_validate({name:raw[name] for name in CandidateProfile.model_fields if name in raw});summary=m2d.summary();summary["profile_conflicts"]=m2d.profile_conflicts(candidate.search_background(),candidate);return summary

    @app.get("/api/m2d/sources")
    def m2d_sources():return m2d.sources()

    @app.get("/api/m2d/tasks")
    def m2d_tasks(status:str|None=None):return m2d.tasks(status)

    @app.get("/api/m2d/states")
    def m2d_states():
        with service.db.transaction() as conn:return {row["job_key"]:dict(row) for row in conn.execute("SELECT * FROM job_operational_state")}

    @app.post("/api/m2d/gmail/import")
    def import_gmail_export(messages:list[EmailExportMessage],limit:int=Query(default=100,ge=1,le=1000),interval_end:str|None=None):
        return GmailExportAdapter(m2d).ingest(messages,limit=limit,interval_end=interval_end)

    @app.post("/api/m2d/export/{stream}")
    def export_jobqueue(stream:Literal["MAJOR","GMAIL","SPECIALIST","REMOTE","CONSOLIDATED"]):
        result=JobQueueWorkbook(m2d).export(stream,service.db.path.parent/"exports")
        return {k:(v.name if k=="path" else v) for k,v in result.items()}

    @app.get("/api/m3/packets")
    def m3_packets(status:str|None=None,include_history:bool=False):return m3.list(status,include_history=include_history)

    @app.post("/api/m3/packets/prepare")
    def prepare_m3_queue():return m3.prepare_queue()

    @app.post("/api/m3/packets/job/{job_key}")
    def prepare_m3_job(job_key:str):
        try:
            result=m3.prepare(job_key)
            from .automatic_drafts import process
            result['automatic_drafts']=process(service.db,engine=m3,packet_id=result['packet_id'])
            return result
        except ValueError as error:raise HTTPException(404 if str(error)=="job_not_found" else 422,str(error)) from None

    @app.get("/api/m3/packets/{packet_id}")
    def m3_packet(packet_id:str):
        result=m3.get(packet_id)
        if not result:raise HTTPException(404,"packet_not_found")
        return result

    @app.put("/api/m3/packets/{packet_id}")
    def edit_m3_packet(packet_id:str,data:PacketEdit):
        try:return m3.edit(packet_id,data)
        except ValueError as error:raise HTTPException(404,str(error)) from None

    @app.post("/api/m3/packets/{packet_id}/questions")
    def add_m3_question(packet_id:str,data:EmployerQuestion):
        try:return {"question_id":m3.add_question(packet_id,data)}
        except ValueError as error:raise HTTPException(404,str(error)) from None

    class AnswerInput(BaseModel):
        answer:str|None=Field(default=None,max_length=50000)
    @app.post("/api/m3/questions/{question_id}/answers")
    def answer_m3_question(question_id:str,data:AnswerInput):
        try:return m3.answer_question(question_id,data.answer)
        except ValueError as error:raise HTTPException(422,str(error)) from None

    @app.post("/api/m3/jobs/{job_key}/contacts")
    def add_m3_contact(job_key:str,data:ContactInput):
        try:
            contact_id=m3.add_contact(job_key,data)
            from .automatic_drafts import process
            packet=m3.by_job(job_key)
            result=process(service.db,engine=m3,packet_id=packet['packet_id']) if packet else {'enabled':False,'saved':0}
            return {'contact_id':contact_id,'automatic_drafts':result}
        except ValueError as error:raise HTTPException(422,str(error)) from None

    def draft_adapter():
        root=service.db.path.parent/"gmail";return GmailDraftAdapter(root/"client_secret.json",root/"compose_token.json")
    @app.get("/api/m3/gmail/status")
    def m3_gmail_status():
        from .automatic_drafts import status
        result={**draft_adapter().status(),**status(service.db)}
        try:result['last_processing']=json.loads((service.db.path.parent/'gmail/automatic-draft-result.json').read_text(encoding='utf-8'))
        except (OSError,ValueError):result['last_processing']=None
        return result

    @app.post('/api/m3/packets/{packet_id}/automatic-draft')
    def automatic_m3_draft(packet_id:str):
        from .automatic_drafts import process
        if not m3.get(packet_id):raise HTTPException(404,'packet_not_found')
        return process(service.db,engine=m3,adapter=draft_adapter(),packet_id=packet_id)

    @app.post("/api/m3/packets/{packet_id}/gmail-draft")
    def create_m3_draft(packet_id:str,data:DraftRequest):
        try:return m3.create_draft(packet_id,data,draft_adapter())
        except ValueError as error:raise HTTPException(409 if "duplicate" in str(error) or "uncertain" in str(error) else 422,str(error)) from None

    @app.post('/api/m3/packets/{packet_id}/draft-preview')
    def draft_preview(packet_id:str):
        from .draft_review import preview
        try:return preview(service.db,packet_id)
        except ValueError as error:raise HTTPException(422,str(error)) from None

    class ExactDraftApproval(BaseModel):
        preview_id:str=Field(pattern='^[0-9a-f]{64}$')
        approved:bool

    @app.post('/api/m3/draft-approvals')
    def approve_exact_draft(data:ExactDraftApproval):
        from .draft_review import approve
        try:return approve(service.db,data.preview_id,getattr(app.state,'r2_draft_adapter',None) or draft_adapter(),approved=data.approved)
        except ValueError as error:raise HTTPException(409,str(error)) from None

    @app.get('/api/browser/applications/{identifier}/resolutions')
    def browser_resolutions(identifier:str):
        from .review_workflow import resolution_report
        try:return resolution_report(service.db,identifier)
        except ValueError as error:raise HTTPException(404,str(error)) from None

    @app.post("/api/m3/draft-operations/{operation_id}/resolve")
    def resolve_m3_draft(operation_id:str,data:DraftResolution):
        try:return m3.resolve_uncertain(operation_id,data.outcome,data.gmail_draft_id)
        except ValueError as error:raise HTTPException(422,str(error)) from None

    @app.post("/api/m3/export")
    def export_m3():
        result=M3Workbook(m3).export(service.db.path.parent/"exports");return {k:(v.name if k=="path" else v) for k,v in result.items()}

    class BrowserBatchInput(BaseModel):
        job_ids:list[str]|None=Field(default=None,max_length=5)
        limit:int=Field(default=5,ge=1,le=5)
        reconstruct_after_progress_review:bool=False

    @app.get('/api/browser/applications')
    def browser_applications(include_history:bool=False):return browser_store.list(include_history=include_history)

    @app.get('/api/email/leads')
    def received_leads(page:int=Query(default=1,ge=1)):
        from .email_research import leads
        return leads(service.db,page)

    @app.get('/api/priority-queue')
    def application_priority():
        from .priority_queue import snapshot
        return snapshot(service.db)

    @app.post('/api/priority-queue/refresh')
    def refresh_application_priority():
        from .priority_queue import refresh
        return refresh(service.db)

    @app.post('/api/email/research')
    def research_received_leads():
        from .email_research import start
        return start(service.db)

    @app.post('/api/email/leads/{identifier}/import')
    def import_received_lead(identifier:str):
        from .email_research import import_lead
        try:return import_lead(service.db,identifier)
        except ValueError as error:raise HTTPException(422,str(error)) from None

    @app.post('/api/email/leads/{identifier}/research')
    def research_received_lead(identifier:str):
        from .email_research import start
        return start(service.db,job_id=identifier)

    @app.get('/api/browser/saved-facts')
    def saved_browser_facts():
        from .application_answers import approved_facts
        profile,facts,sources,_=approved_facts(service.db)
        names={'full_name':'Legal name','surname_fallbacks':'Required surname formatting fallbacks','phone_format':'Phone format','country':'Country of residence','city':'Current city','current_company':'Current employer','current_title':'Current job title','notice_period':'Notice period','expected_compensation':'Expected compensation'}
        return {'profile_version':profile.get('version'),'facts':[{'key':key,'label':label,'value':facts[key],'source':'Saved user answer' if key in profile.get('approved_application_answers',{}) else 'Approved answer bank'} for key,label in names.items() if key in facts]}

    @app.get('/api/browser/progress')
    def browser_progress():
        from .review_workflow import progress
        return progress(service.db)

    @app.post('/api/browser/sync')
    def browser_sync():
        from .browser_applications import launch_sync_worker
        try:return {'state':'SYNCHRONIZING','worker_pid':launch_sync_worker(service.db)}
        except ValueError as error:raise HTTPException(409,str(error)) from None

    @app.get('/api/browser/applications/{identifier}/questions')
    def browser_questions(identifier:str):
        from .review_workflow import pending_questions
        try:return pending_questions(service.db,identifier)
        except ValueError as error:raise HTTPException(404,str(error)) from None

    class ReviewAnswer(BaseModel):
        key:str=Field(max_length=100)
        value:str=Field(min_length=1,max_length=10000)
        reuse:bool=False
    class ReviewAnswers(BaseModel):
        answers:list[ReviewAnswer]=Field(min_length=1,max_length=50)

    @app.post('/api/browser/applications/{identifier}/answers')
    def browser_answers(identifier:str,data:ReviewAnswers):
        from .review_workflow import save_answers
        from .browser_applications import launch_sync_worker
        try:
            result=save_answers(service.db,identifier,[v.model_dump() for v in data.answers])
            result['worker_pid']=launch_sync_worker(service.db,identifier)
            return result
        except ValueError as error:raise HTTPException(422,str(error)) from None

    @app.post('/api/browser/batches')
    def browser_batch(data:BrowserBatchInput):
        from .browser_applications import launch_worker
        try:
            from .browser_workers import BrowserWorkers
            workers=BrowserWorkers(service.db);workers.recover_expired()
            if any(w['state'] in {'QUEUED','RUNNING'} for w in workers.list()):raise ValueError('workflow_already_running')
            batch=browser_store.batch(data.job_ids,data.limit,data.reconstruct_after_progress_review)
            if batch['selected']:batch['worker_pid']=launch_worker(service.db,batch['batch_id'])
            return batch
        except ValueError as error:raise HTTPException(422,str(error)) from None

    @app.post('/api/browser/applications/{identifier}/switch')
    def browser_switch(identifier:str):
        from .browser_applications import switch_tab
        try:return switch_tab(service.db,identifier)
        except ValueError as error:raise HTTPException(409,str(error)) from None

    @app.post('/api/browser/connect/{portal}')
    def browser_connect(portal:str):
        from .browser_applications import connect_login
        from playwright.sync_api import Error as BrowserError
        try:return connect_login(service.db,portal)
        except ValueError as error:raise HTTPException(409,str(error)) from None
        except BrowserError:raise HTTPException(409,'Login tab could not be opened or loaded. Check the dedicated Chrome window before retrying.') from None

    @app.post('/api/browser/applications/{identifier}/inspect')
    def browser_inspect(identifier:str):
        from .browser_applications import reinspect
        try:return reinspect(service.db,identifier)
        except ValueError as error:raise HTTPException(409,str(error)) from None

    @app.post('/api/browser/applications/{identifier}/resume')
    def browser_resume(identifier:str):
        from .browser_applications import launch_worker
        try:
            item=browser_store.get(identifier);browser_store.job(item['job_id'],require_verified=True)
            if item['state'] in {'SESSION_LOST','USER_REPORTED_SUBMITTED','SUBMISSION_CONFIRMED'}:raise ValueError('cannot_resume_without_progress_review')
            browser_store.update(identifier,state='PREPARING')
            launch_worker(service.db,item['batch_id'],allow_upload=False,only_application=item['id'])
            return {'state':'PREPARING','uploads_allowed':False}
        except ValueError as error:raise HTTPException(409,str(error)) from None

    @app.post('/api/browser/applications/{identifier}/reported-submitted')
    def browser_report_submitted(identifier:str):
        try:
            browser_store.get(identifier)
            browser_store.update(identifier,state='USER_REPORTED_SUBMITTED')
            from .application_state import submission_projection
            with service.db.transaction() as conn:result=submission_projection(conn,browser_store.get(identifier)['job_id'])
            return {'state':result['application_outcome'],**result}
        except ValueError as error:raise HTTPException(404,str(error)) from None

    return app

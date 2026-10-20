"""Persistent M2D coverage, queue, identity and handoff orchestration."""
from __future__ import annotations
import hashlib,html,json,re,uuid
from datetime import datetime,timedelta,timezone
from urllib.parse import parse_qsl,unquote,urlsplit,urlunsplit,urlencode
from .database import now
from .m2d_models import CoverageStatus,EmailExportMessage,OperationalFacts,Readiness,TriState
from .m2d_sources import PRIORITY_EMPLOYERS,SOURCES,SOURCE_DIAGNOSTICS
from .models import clean,key
from .alert_links import alert_links

SNAPSHOT_SCHEMA="JobQueue-v1"

def canonical_url(url:str|None)->str|None:
    if not url:return None
    parsed=urlsplit(url.strip())
    if parsed.scheme.lower() not in {"http","https"} or not parsed.netloc:return None
    host=parsed.netloc.lower().removeprefix("www.")
    path=re.sub(r"/+","/",parsed.path).rstrip("/") or "/"
    # Query identity is significant for Indeed and Glassdoor vacancies.
    identity_query=[(k,v) for k,v in parse_qsl(parsed.query) if k in {"jk","jl","jobListingId"}]
    if host in {'glassdoor.co.in','glassdoor.com'}:
        identifier=dict(identity_query).get('jobListingId') or dict(identity_query).get('jl')
        if identifier and re.fullmatch(r'\d+',identifier):return urlunsplit(('https',host,'/partner/jobListing.htm',urlencode({'jobListingId':identifier}),''))
    return urlunsplit(("https",host,path,urlencode(sorted(identity_query)),""))

def stable_job_key(*,url:str|None,source_id:str,provider_id:str|None,company:str,title:str,location:str="")->str:
    link=canonical_url(url)
    identity=["url",link] if link else ["provider",source_id,provider_id] if provider_id else ["natural",key(company),key(title),key(location),source_id]
    return hashlib.sha256(json.dumps(identity,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()

def classify_readiness(facts:OperationalFacts,strong_fit:bool=True)->tuple[Readiness,list[str],str|None]:
    hard={"active":facts.active,"india_eligible":facts.india_eligible,"headcount":facts.headcount,"direct_permanent_payroll":facts.direct_permanent_payroll,"mandatory_requirements":facts.mandatory_requirements}
    failed=[name for name,state in hard.items() if state==TriState.FAIL]
    if failed:return Readiness.EXCLUDED,[],"failed: "+", ".join(failed)
    missing=[name for name,state in hard.items() if state in {TriState.UNKNOWN,TriState.CONFLICT}]
    if not missing:
        if facts.verified_recipient==TriState.PASS:return Readiness.EMAIL_DRAFT_READY,[],None
        return Readiness.FULLY_VERIFIED_APPLICATION_READY,(["verified_recipient"] if facts.verified_recipient==TriState.UNKNOWN else []),None
    if facts.active==TriState.PASS and strong_fit:return Readiness.READY_FOR_PORTAL_REVIEW,missing,None
    return Readiness.PROMISING_NEEDS_VERIFICATION,missing,None

def headcount_state(headcount:int|None,work_mode:str)->TriState:
    if headcount is None:return TriState.UNKNOWN
    threshold=500 if work_mode=="remote" else 1000
    return TriState.PASS if headcount>=threshold else TriState.FAIL

class M2DEngine:
    def __init__(self,db):self.db=db

    def seed(self):
        stamp=now()
        with self.db.transaction() as conn:
            for item in SOURCES:
                if item['source_id']=='gmail' and conn.execute("SELECT 1 FROM gmail_live_runs WHERE status='COMPLETED' LIMIT 1").fetchone():
                    item=item | {'implementation_state':'IMPLEMENTED_LIVE_VERIFIED'}
                diagnostic=SOURCE_DIAGNOSTICS[item["source_id"]];blocked=diagnostic["root_cause"] if item["implementation_state"]=="ACCESS_BLOCKED" else None
                coverage="ACCESS_BLOCKED" if item["implementation_state"]=="ACCESS_BLOCKED" else "UNATTEMPTED"
                conn.execute("""INSERT INTO m2d_sources(source_id,display_name,stream,owner,official_url,implementation_state,connector,reference_time_ist,coverage_status,filters,pagination_strategy,blocker,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(source_id) DO UPDATE SET display_name=excluded.display_name,stream=excluded.stream,owner=excluded.owner,official_url=excluded.official_url,
                    implementation_state=excluded.implementation_state,connector=excluded.connector,reference_time_ist=excluded.reference_time_ist,filters=excluded.filters,pagination_strategy=excluded.pagination_strategy,
                    coverage_status=CASE WHEN m2d_sources.coverage_status='ACCESS_BLOCKED' AND excluded.coverage_status<>'ACCESS_BLOCKED' THEN 'UNATTEMPTED' ELSE m2d_sources.coverage_status END,
                    blocker=CASE WHEN excluded.coverage_status='ACCESS_BLOCKED' THEN excluded.blocker WHEN m2d_sources.coverage_status='ACCESS_BLOCKED' THEN NULL ELSE m2d_sources.blocker END,updated_at=excluded.updated_at""",
                    (item["source_id"],item["display_name"],item["stream"],item["owner"],item["official_url"],item["implementation_state"],item["connector"],item["reference_time_ist"],coverage,json.dumps(diagnostic,sort_keys=True),"bounded_provider_cursor" if item["connector"] else "import_cursor",blocked,stamp))
            for name in PRIORITY_EMPLOYERS:
                employer_key=key(name)
                conn.execute("INSERT OR IGNORE INTO employer_registry(employer_key,name,updated_at) VALUES(?,?,?)",(employer_key,name,stamp))

    def sources(self):
        with self.db.transaction() as conn:return [dict(row) for row in conn.execute("SELECT * FROM m2d_sources ORDER BY stream,display_name")]

    def employers(self):
        with self.db.transaction() as conn:return [dict(row) for row in conn.execute("SELECT * FROM employer_registry ORDER BY name")]

    def enqueue(self,*,kind,source_id,stream,category,payload=None,job_key=None,priority=0,due_at=None,max_attempts=2,task_id=None):
        stamp=now();task_id=task_id or hashlib.sha256(json.dumps([kind,source_id,job_key,category,payload or {}],sort_keys=True,separators=(",",":")).encode()).hexdigest()
        with self.db.transaction() as conn:
            conn.execute("""INSERT OR IGNORE INTO m2d_tasks(task_id,kind,source_id,job_key,stream,category,payload,priority,due_at,max_attempts,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",(task_id,kind,source_id,job_key,stream,category,json.dumps(payload or {},sort_keys=True),priority,due_at or stamp,max_attempts,stamp,stamp))
        return task_id

    def seed_discovery_tasks(self):
        for source in self.sources():
            if source["implementation_state"]!="ACCESS_BLOCKED":self.enqueue(kind="DISCOVERY",source_id=source["source_id"],stream=source["stream"],category="SOURCE_SWEEP",payload={"cursor":source["cursor"]},priority=10)

    def plan_week(self,at=None):
        stamp=at or now();week=datetime.fromisoformat(stamp.replace("Z","+00:00")).strftime("%G-W%V");created=[]
        for source in self.sources():
            if source["implementation_state"]=="IMPLEMENTED_LIVE_VERIFIED":
                created.append(self.enqueue(kind="DISCOVERY",source_id=source["source_id"],stream=source["stream"],category="SOURCE_SWEEP",payload={"week":week,"bounded":True},priority=20,task_id=hashlib.sha256(f"{week}:source:{source['source_id']}".encode()).hexdigest()))
        employers=list(PRIORITY_EMPLOYERS)
        for index in range(0,len(employers),5):
            group=employers[index:index+5];created.append(self.enqueue(kind="DISCOVERY",source_id="employer-careers",stream="MAJOR",category="EMPLOYER_GROUP",payload={"week":week,"employers":group},priority=15,task_id=hashlib.sha256(f"{week}:employers:{index}".encode()).hexdigest()))
        for category in ("FRONTEND","FRONTEND_LEADERSHIP","AI_GENAI","FULLSTACK_AI"):
            created.append(self.enqueue(kind="DISCOVERY",source_id="employer-careers",stream="MAJOR",category="ROLE_ROTATION",payload={"week":week,"category":category},priority=12,task_id=hashlib.sha256(f"{week}:category:{category}".encode()).hexdigest()))
        due=(datetime.fromisoformat(stamp.replace("Z","+00:00"))+timedelta(days=7)).isoformat().replace("+00:00","Z")
        with self.db.transaction() as conn:conn.execute("UPDATE m2d_sources SET next_due=COALESCE(next_due,?),updated_at=?",(due,stamp))
        return created

    def profile_conflicts(self,background,profile):
        conflicts=[]
        if background.total_years!=7:conflicts.append({"field":"search_background.total_years","stored":background.total_years,"schedule":7})
        if profile.total_experience_years is not None and profile.total_experience_years!=7:conflicts.append({"field":"candidate.total_experience_years","stored":profile.total_experience_years,"schedule":7})
        expected={"delhi ncr","noida","greater noida","gurugram","mohali","chandigarh","remote india"};stored=set(profile.preferred_locations)
        if not expected<=stored:conflicts.append({"field":"candidate.preferred_locations","stored":sorted(stored),"schedule":sorted(expected)})
        return conflicts

    def reconcile_discovery_run(self,run):
        if not run or run["status"]=="RUNNING":return None
        with self.db.transaction() as conn:
            existing=conn.execute("SELECT snapshot_id FROM m2d_snapshots WHERE run_id=? AND stream='PIPELINE'",(run["id"],)).fetchone()
        if existing:return None
        mapping={"greenhouse":"greenhouse","lever":"lever","remoteok":"remoteok","wwr":"wwr","smartrecruiters":"smartrecruiters","amazon":"employer-careers"};counts={"sources":len(run.get("sources",[])),"new":run["metrics"].get("new_jobs",0),"updated":run["metrics"].get("updated_jobs",0),"pending":0}
        with self.db.transaction() as conn:legacy={row["id"]:dict(row) for row in conn.execute("SELECT id,provider,checkpoint FROM sources")}
        groups={}
        for item in run.get("sources",[]):
            if item["status"]=="SKIPPED":continue
            configured=legacy.get(item["source_id"]);source_id=mapping.get(configured["provider"] if configured else "")
            if not source_id:continue
            checkpoint=json.loads(configured["checkpoint"] or "{}") if configured else {};complete=bool(checkpoint.get("complete"))
            group=groups.setdefault(source_id,{"items":[],"checkpoints":{},"rejected":0})
            group["items"].append(item);group["checkpoints"][item["source_id"]]=checkpoint
            group["rejected"]+=int(item.get("metrics",{}).get("rejected_records") or 0)
        for source_id,group in groups.items():
            statuses={item["status"] for item in group["items"]};all_complete=all(bool(value.get("complete")) for value in group["checkpoints"].values())
            if "FAILED" in statuses or "PARTIAL" in statuses:coverage=CoverageStatus.PARTIALLY_SEARCHED if statuses & {"SUCCESS","PARTIAL"} else CoverageStatus.ATTEMPTED_NO_USABLE_RESULTS
            elif statuses=={"SUCCESS"}:coverage=CoverageStatus.EXHAUSTIVELY_SEARCHED if all_complete else CoverageStatus.MEANINGFULLY_SEARCHED
            else:continue
            backlog=group["rejected"] if coverage==CoverageStatus.PARTIALLY_SEARCHED else 0;counts["pending"]+=backlog
            errors=[item.get("error") for item in group["items"] if item.get("error")]
            blocker=("rejected_records:"+str(backlog)) if backlog else ("; ".join(errors) or None)
            self.record_coverage(source_id,coverage,scope={"configured_sources":[item["source_id"] for item in group["items"]],"run_id":run["id"]},cursor=group["checkpoints"],blocker=blocker,backlog=backlog,exhausted=coverage==CoverageStatus.EXHAUSTIVELY_SEARCHED)
            with self.db.transaction() as conn:
                conn.execute("UPDATE m2d_tasks SET status='COMPLETED',checkpoint=?,blocker=?,updated_at=? WHERE kind='DISCOVERY' AND source_id=? AND category='SOURCE_SWEEP' AND status='PENDING'",(json.dumps({"run_id":run["id"],"coverage":coverage.value},sort_keys=True),blocker,now(),source_id))
        return self.snapshot(run_id=run["id"],stream="PIPELINE",status="COMPLETED" if run["status"]=="COMPLETED" else "PARTIAL" if run["status"]=="PARTIAL" else "FAILED",started_at=run["started_at"],counts=counts)

    def seed_verification_tasks(self):
        """Persist every strong-fit unresolved hard fact; execution may remain bounded."""
        created=[]
        with self.db.transaction() as conn:
            rows=conn.execute("""SELECT s.job_key,s.readiness,s.missing_facts,j.match_score
                FROM job_operational_state s LEFT JOIN jobs j ON j.id=s.job_id
                WHERE s.readiness IN ('READY_FOR_PORTAL_REVIEW','PROMISING_NEEDS_VERIFICATION')
                ORDER BY s.job_key""").fetchall()
        for row in rows:
            if row["match_score"] is not None and float(row["match_score"])<70:continue
            for fact in json.loads(row["missing_facts"] or "[]"):
                task_id=hashlib.sha256(f"verify:{row['job_key']}:{fact}".encode()).hexdigest()
                created.append(self.enqueue(kind="VERIFICATION",source_id=None,stream="PIPELINE",category=fact.upper(),job_key=row["job_key"],payload={"fact":fact},priority=30,task_id=task_id))
        return created

    def execute_verification_tasks(self,limit=12):
        """Consume existing evidence without treating a task run as a new source check."""
        from .policy_hooks import check
        check('research_worker','VERIFICATION')
        stamp=now();lease=(datetime.fromisoformat(stamp.replace("Z","+00:00"))+timedelta(seconds=120)).isoformat().replace("+00:00","Z")
        with self.db.transaction() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows=conn.execute("""SELECT t.*,j.activity_status,j.eligibility_state,j.required_skills,j.canonical_application_url,j.application_url,j.work_mode,
                       s.active_state,s.india_state,s.headcount_state,s.payroll_state,s.verification,s.recipient_state,s.job_id
                FROM m2d_tasks t JOIN job_operational_state s ON s.job_key=t.job_key JOIN jobs j ON j.id=s.job_id
                WHERE t.kind='VERIFICATION' AND t.category<>'EMAIL_OFFICIAL_JD' AND t.status='PENDING' AND t.due_at<=? AND t.attempts<t.max_attempts
                ORDER BY CASE WHEN julianday(?) - julianday(t.created_at)>=1 THEN 0 ELSE 1 END,
                  CASE WHEN julianday(?) - julianday(t.created_at)>=1 THEN t.created_at END,
                  j.match_score DESC,t.due_at,t.task_id LIMIT ?""",(stamp,stamp,stamp,limit)).fetchall()
            for row in rows:conn.execute("UPDATE m2d_tasks SET status='RUNNING',lease_until=?,attempts=attempts+1,updated_at=? WHERE task_id=?",(lease,stamp,row["task_id"]))
        result={"considered":len(rows),"attempted":len(rows),"resolved":0,"blocked":0,"deferred":0,"outcomes":[]}
        for row in rows:
            fact=json.loads(row["payload"] or "{}").get("fact",row["category"].casefold())
            state=None;gate_name=None;gate=None;evidence_time=None
            fact_gates={
                "active":"active","active_vacancy":"active",
                "india_eligible":"india_employment","india_eligibility":"india_employment",
                "headcount":"employer_size","direct_permanent_payroll":"payroll",
            }
            if fact in fact_gates:
                from .eligibility import assess_hard_eligibility
                gate_name=fact_gates[fact]
                with self.db.transaction() as conn:
                    job=dict(conn.execute("SELECT * FROM jobs WHERE id=?",(row["job_id"],)).fetchone())
                    evidence=[dict(item) for item in conn.execute("SELECT * FROM job_evidence WHERE job_key=?",(row["job_key"],))]
                    references=[dict(item) for item in conn.execute("SELECT listing_url,application_url,last_seen,imported_at FROM source_references WHERE job_id=?",(row["job_id"],))]
                assessment=assess_hard_eligibility(job,evidence,references,at=datetime.fromisoformat(stamp.replace("Z","+00:00")))
                gate=assessment["gates"][gate_name]
                state=gate["state"]
                evidence_time=max((item["verified_at"] for item in gate["evidence"]),default=None)
            elif fact=="mandatory_requirements":
                from .requirements import assess_requirements,persist_assessment
                with self.db.transaction() as conn:
                    profile=json.loads(conn.execute('SELECT config FROM candidate_profiles_v2 ORDER BY version DESC LIMIT 1').fetchone()[0])
                    job=dict(conn.execute('SELECT * FROM jobs WHERE id=?',(row['job_id'],)).fetchone())
                    evidence=[dict(e) for e in conn.execute('SELECT * FROM job_evidence WHERE job_key=?',(row['job_key'],))]
                verdict=assess_requirements(profile,job,evidence);state=verdict['state']
                with self.db.transaction() as conn:persist_assessment(conn,job['id'],verdict)
            if state:
                facts=OperationalFacts(active=TriState(row["active_state"]),india_eligible=TriState(row["india_state"]),headcount=TriState(row["headcount_state"]),direct_permanent_payroll=TriState(row["payroll_state"]),mandatory_requirements=TriState.PASS if row["verification"]=="FULLY_VERIFIED" else TriState.UNKNOWN,verified_recipient=TriState(row["recipient_state"]),work_mode=row["work_mode"] if row["work_mode"] in {"onsite","hybrid","remote"} else "unknown")
                if gate_name=="active":facts=facts.model_copy(update={"active":TriState(state)})
                elif gate_name=="india_employment":facts=facts.model_copy(update={"india_eligible":TriState(state)})
                elif gate_name=="employer_size":facts=facts.model_copy(update={"headcount":TriState(state)})
                elif gate_name=="payroll":facts=facts.model_copy(update={"direct_permanent_payroll":TriState(state)})
                elif fact=="mandatory_requirements":facts=facts.model_copy(update={"mandatory_requirements":TriState(state)})
                self.set_operational_state(row["job_key"],facts,job_id=row["job_id"],strong_fit=True)
                resolved=state in {'PASS','FAIL'};task_state='COMPLETED' if resolved else 'BLOCKED' if gate_name or state=='CONFLICT' else 'PARTIAL'
                checkpoint={'fact':fact,'verdict':state,'resolved_at':stamp}
                if gate_name:
                    checkpoint.update(
                        evidence_verified_at=evidence_time,
                        evidence_url=gate['evidence'][0]['evidence_url'] if gate['evidence'] else None,
                        retry_condition='Retry when a current sourced record becomes available.',
                    )
                self.finish_task(row['task_id'],status=task_state,checkpoint=checkpoint,blocker=None if resolved else gate['reason'] if gate_name else 'Current mandatory requirement assessment remains unresolved.')
                result['resolved' if resolved else 'blocked' if gate_name or state=='CONFLICT' else 'deferred']+=1;outcome='resolved' if resolved else state.casefold()
            else:
                reason={"headcount":"Employer legal-entity headcount needs an external sourced check.","direct_permanent_payroll":"The vacancy does not establish permanent direct-employer payroll.","mandatory_requirements":"Mandatory requirements are not structured in the stored vacancy."}.get(fact,"No sufficient stored evidence for this fact.")
                retry="Retry when a current official vacancy or sourced employer record changes."
                status="BLOCKED" if fact in {"headcount","direct_permanent_payroll"} else "PARTIAL";self.finish_task(row["task_id"],status=status,checkpoint={"fact":fact,"next_action":"Research a current factual source.","retry_condition":retry},blocker=reason);result["blocked" if status=="BLOCKED" else "deferred"]+=1;outcome=status.casefold()
            result["outcomes"].append({"task_id":row["task_id"],"job_key":row["job_key"],"fact":fact,"outcome":outcome})
        return result

    def recover_expired(self,at=None):
        at=at or now()
        with self.db.transaction() as conn:
            result=conn.execute("UPDATE m2d_tasks SET status='PENDING',lease_until=NULL,blocker='interrupted_lease',updated_at=? WHERE status='RUNNING' AND lease_until<?",(at,at))
            return result.rowcount

    def claim(self,limit=4,lease_seconds=120,at=None):
        at=at or now();lease=(datetime.fromisoformat(at.replace("Z","+00:00"))+timedelta(seconds=lease_seconds)).isoformat().replace("+00:00","Z")
        with self.db.transaction() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows=conn.execute("""WITH ranked AS (SELECT *,row_number() OVER(PARTITION BY stream ORDER BY priority DESC,due_at,task_id) AS rn
                FROM m2d_tasks WHERE status='PENDING' AND due_at<=? AND attempts<max_attempts)
                SELECT * FROM ranked ORDER BY rn,priority DESC,due_at,stream,task_id LIMIT ?""",(at,limit)).fetchall()
            ids=[row["task_id"] for row in rows]
            from .policy_hooks import check
            for row in rows:check('research_worker',row['kind'])
            for task_id in ids:conn.execute("UPDATE m2d_tasks SET status='RUNNING',lease_until=?,attempts=attempts+1,updated_at=? WHERE task_id=?",(lease,at,task_id))
        return [dict(row) for row in rows]

    def finish_task(self,task_id,*,status="COMPLETED",checkpoint=None,blocker=None,continuation=None):
        if status not in {"COMPLETED","PARTIAL","BLOCKED","FAILED"}:raise ValueError("invalid_task_status")
        stamp=now()
        with self.db.transaction() as conn:
            row=conn.execute("SELECT * FROM m2d_tasks WHERE task_id=?",(task_id,)).fetchone()
            if not row or row["status"]!="RUNNING":return False
            conn.execute("UPDATE m2d_tasks SET status=?,lease_until=NULL,checkpoint=?,blocker=?,updated_at=? WHERE task_id=?",(status,json.dumps(checkpoint or {},sort_keys=True),blocker,stamp,task_id))
        if continuation:
            self.enqueue(kind=row["kind"],source_id=row["source_id"],job_key=row["job_key"],stream=row["stream"],category=row["category"],payload=continuation,priority=row["priority"],task_id=hashlib.sha256((task_id+json.dumps(continuation,sort_keys=True)).encode()).hexdigest())
        return True

    def tasks(self,status=None):
        with self.db.transaction() as conn:
            rows=conn.execute("SELECT * FROM m2d_tasks"+(" WHERE status=?" if status else "")+" ORDER BY due_at,priority DESC,task_id",([status] if status else [])).fetchall()
            return [dict(row) for row in rows]

    def record_coverage(self,source_id,status:CoverageStatus,*,scope=None,cursor=None,blocker=None,backlog=0,exhausted=False):
        if status==CoverageStatus.EXHAUSTIVELY_SEARCHED and not exhausted:raise ValueError("exhaustive_requires_traversal_evidence")
        stamp=now();meaningful=stamp if status in {CoverageStatus.MEANINGFULLY_SEARCHED,CoverageStatus.EXHAUSTIVELY_SEARCHED} else None
        with self.db.transaction() as conn:
            result=conn.execute("""UPDATE m2d_sources SET coverage_status=?,bounded_scope=?,cursor=?,last_attempt=?,meaningful_success=COALESCE(?,meaningful_success),
                blocker=?,attempts=attempts+1,backlog=?,updated_at=? WHERE source_id=?""",(status.value,json.dumps(scope or {},sort_keys=True),json.dumps(cursor or {},sort_keys=True),stamp,meaningful,blocker,backlog,stamp,source_id))
            return result.rowcount==1

    def coverage(self):
        all_rows=self.sources();rows=[row for row in all_rows if row["stream"]!="PIPELINE"];total=len(rows)
        attempted=sum(r["coverage_status"]!="UNATTEMPTED" for r in rows);meaningful=sum(r["coverage_status"] in {"MEANINGFULLY_SEARCHED","EXHAUSTIVELY_SEARCHED"} for r in rows);exhaustive=sum(r["coverage_status"]=="EXHAUSTIVELY_SEARCHED" for r in rows)
        streams={}
        for row in rows:
            item=streams.setdefault(row["stream"],{"configured":0,"attempted":0,"meaningful":0,"exhaustive":0,"blocked":0})
            item["configured"]+=1;item["attempted"]+=row["coverage_status"]!="UNATTEMPTED";item["meaningful"]+=row["coverage_status"] in {"MEANINGFULLY_SEARCHED","EXHAUSTIVELY_SEARCHED"};item["exhaustive"]+=row["coverage_status"]=="EXHAUSTIVELY_SEARCHED";item["blocked"]+=row["coverage_status"]=="ACCESS_BLOCKED"
        return {"configured":total,"attempted":attempted,"meaningful":meaningful,"exhaustive":exhaustive,"contracts":len(all_rows)-len(rows),"streams":streams,"claim":"configured_discovery_sources_only"}

    def observe(self,*,stream,source_id,provider_id,url,company,title,location="",evidence=None,email_received_at=None,snapshot_id=None):
        job_key=stable_job_key(url=url,source_id=source_id,provider_id=provider_id,company=company,title=title,location=location);link=canonical_url(url);stamp=now();oid=hashlib.sha256(json.dumps([source_id,provider_id,link],separators=(",",":")).encode()).hexdigest();details={"company":clean(company),"title":clean(title),"location":clean(location)}|(evidence or {})
        with self.db.transaction() as conn:
            conn.execute("""INSERT INTO job_observations(observation_id,job_key,stream,source_id,provider_id,canonical_url,observed_at,email_received_at,evidence,snapshot_id)
                VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(observation_id) DO UPDATE SET evidence=excluded.evidence,snapshot_id=COALESCE(excluded.snapshot_id,job_observations.snapshot_id)""",
                (oid,job_key,stream,source_id,provider_id,link,stamp,email_received_at,json.dumps(details,sort_keys=True),snapshot_id))
            # Specific alert/import leads remain visible in review exports before
            # an official JD establishes activity, employer or eligibility.
            facts=OperationalFacts();readiness,missing,reason=classify_readiness(facts)
            conn.execute("""INSERT OR IGNORE INTO job_operational_state VALUES(?,NULL,'UNKNOWN','UNKNOWN','UNVERIFIED',?,'UNKNOWN','UNKNOWN','UNKNOWN','UNKNOWN','UNKNOWN',?,?,?)""",
                (job_key,readiness.value,json.dumps(missing),reason,stamp))
        return job_key

    def sync_existing_jobs(self):
        """Add observations/state for existing jobs without changing their canonical rows."""
        with self.db.transaction() as conn:
            rows=conn.execute("""SELECT j.*,r.source ref_source,r.source_key,r.listing_url ref_url,s.provider
                FROM jobs j LEFT JOIN source_references r ON r.job_id=j.id LEFT JOIN sources s ON s.id=r.source ORDER BY j.id,r.id""").fetchall()
            seen=set();count=0
            for row in rows:
                if row['ref_source']=='gmail':continue
                stream="REMOTE" if row["provider"] in {"remoteok","wwr"} else "MAJOR"
                source_id=row["ref_source"] or row["source"] or "local-import";provider_id=row["source_key"]
                link=row["canonical_application_url"] or row["listing_url"] or row["application_url"] or row["ref_url"]
                oid=hashlib.sha256(json.dumps([source_id,provider_id,canonical_url(link)],separators=(",",":")).encode()).hexdigest();stamp=row["last_seen"] or row["updated_at"] or now();details={"company":row["company"],"title":row["title"],"location":row["location"],"job_id":row["id"],"published_at":row["published_at"],"publication_precision":row["timestamp_confidence"]}
                conn.execute("""INSERT INTO job_observations(observation_id,job_key,stream,source_id,provider_id,canonical_url,observed_at,evidence)
                    VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(source_id,provider_id,canonical_url) DO UPDATE SET observed_at=MAX(job_observations.observed_at,excluded.observed_at),evidence=excluded.evidence""",(oid,row["id"],stream,source_id,provider_id,canonical_url(link),stamp,json.dumps(details,sort_keys=True)))
                if row["id"] not in seen:
                    active=TriState.PASS if row["activity_status"]=="ACTIVE" else TriState.FAIL if row["activity_status"]=="CLOSED" else TriState.UNKNOWN
                    india=TriState.PASS if row["eligibility_state"]=="ELIGIBLE" else TriState.FAIL if row["eligibility_state"]=="INELIGIBLE" else TriState.UNKNOWN
                    facts=OperationalFacts(active=active,india_eligible=india,mandatory_requirements=TriState.UNKNOWN,work_mode=row["work_mode"] if row["work_mode"] in {"onsite","hybrid","remote"} else "unknown");readiness,missing,reason=classify_readiness(facts,float(row["match_score"] or 0)>=70);lifecycle="ACTIVE" if active==TriState.PASS else "CLOSED" if active==TriState.FAIL else "UNKNOWN";eligibility="ELIGIBLE" if india==TriState.PASS else "INELIGIBLE" if india==TriState.FAIL else "UNKNOWN";verification="FULLY_VERIFIED" if readiness in {Readiness.FULLY_VERIFIED_APPLICATION_READY,Readiness.EMAIL_DRAFT_READY} else "PARTIAL" if readiness==Readiness.READY_FOR_PORTAL_REVIEW else "UNVERIFIED"
                    conn.execute("INSERT OR IGNORE INTO job_operational_state VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(row["id"],row["id"],lifecycle,eligibility,verification,readiness.value,facts.headcount.value,facts.direct_permanent_payroll.value,india.value,active.value,facts.verified_recipient.value,json.dumps(missing),reason,now()))
                    seen.add(row["id"]);count+=1
        return count

    def set_operational_state(self,job_key,facts:OperationalFacts,*,job_id=None,strong_fit=True):
        readiness,missing,reason=classify_readiness(facts,strong_fit);stamp=now();lifecycle="ACTIVE" if facts.active==TriState.PASS else "CLOSED" if facts.active==TriState.FAIL else "UNKNOWN";eligibility="ELIGIBLE" if facts.india_eligible==TriState.PASS else "INELIGIBLE" if facts.india_eligible==TriState.FAIL else "UNKNOWN";verification="FULLY_VERIFIED" if readiness in {Readiness.FULLY_VERIFIED_APPLICATION_READY,Readiness.EMAIL_DRAFT_READY} else "PARTIAL" if readiness==Readiness.READY_FOR_PORTAL_REVIEW else "UNVERIFIED"
        with self.db.transaction() as conn:
            conn.execute("""INSERT INTO job_operational_state VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(job_key) DO UPDATE SET job_id=COALESCE(excluded.job_id,job_operational_state.job_id),lifecycle=excluded.lifecycle,eligibility=excluded.eligibility,verification=excluded.verification,readiness=excluded.readiness,headcount_state=excluded.headcount_state,payroll_state=excluded.payroll_state,india_state=excluded.india_state,active_state=excluded.active_state,recipient_state=excluded.recipient_state,missing_facts=excluded.missing_facts,exclusion_reason=excluded.exclusion_reason,updated_at=excluded.updated_at""",
                (job_key,job_id,lifecycle,eligibility,verification,readiness.value,facts.headcount.value,facts.direct_permanent_payroll.value,facts.india_eligible.value,facts.active.value,facts.verified_recipient.value,json.dumps(missing),reason,stamp))
        from .priority_queue import after_evidence_change
        after_evidence_change(self.db)
        return {"readiness":readiness.value,"missing_facts":missing,"exclusion_reason":reason}

    def record_evidence(self,job_key,kind,state,*,factual,evidence_url,verified_at=None,inference=None):
        """Cache a scoped factual check without mixing its inference into source text."""
        stamp=verified_at or now();checksum=hashlib.sha256(json.dumps([job_key,kind,state,factual,evidence_url],ensure_ascii=False,separators=(",",":")).encode()).hexdigest();evidence_id=hashlib.sha256(f"{job_key}:{kind}:{evidence_url}".encode()).hexdigest()
        with self.db.transaction() as conn:
            conn.execute("""INSERT INTO job_evidence(evidence_id,job_key,kind,state,factual,inference,evidence_url,observed_at,verified_at,checksum)
              VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(evidence_id) DO UPDATE SET state=excluded.state,factual=excluded.factual,inference=excluded.inference,observed_at=excluded.observed_at,verified_at=excluded.verified_at,checksum=excluded.checksum""",(evidence_id,job_key,kind,state,factual,inference,evidence_url,stamp,stamp,checksum))
        from .priority_queue import after_evidence_change
        after_evidence_change(self.db)
        return evidence_id

    def snapshot(self,*,run_id,stream,status,started_at,counts,artifact_name=None,artifact_checksum=None):
        finished=now()
        if status not in {"COMPLETED","PARTIAL","FAILED"}:raise ValueError("invalid_snapshot_status")
        with self.db.transaction() as conn:
            distinct=conn.execute("SELECT count(DISTINCT job_key) FROM job_observations WHERE stream=?",(stream,)).fetchone()[0];observations=conn.execute("SELECT count(1) FROM job_observations WHERE stream=?",(stream,)).fetchone()[0]
            body={"run_id":run_id,"stream":stream,"schema":SNAPSHOT_SCHEMA,"status":status,"started_at":started_at,"finished_at":finished,"distinct_jobs":distinct,"observations":observations,"counts":counts,"artifact_name":artifact_name,"artifact_checksum":artifact_checksum}
            snapshot_id=hashlib.sha256(json.dumps(body,sort_keys=True,separators=(",",":")).encode()).hexdigest()
            conn.execute("INSERT OR IGNORE INTO m2d_snapshots VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(snapshot_id,run_id,stream,SNAPSHOT_SCHEMA,status,started_at,finished,distinct,observations,json.dumps(counts,sort_keys=True),artifact_name,artifact_checksum,finished))
        return snapshot_id

    def consume(self,consumer,snapshot_id):
        with self.db.transaction() as conn:
            if not conn.execute("SELECT 1 FROM m2d_snapshots WHERE snapshot_id=?",(snapshot_id,)).fetchone():raise ValueError("snapshot_not_found")
            current=conn.execute("SELECT snapshot_id FROM m2d_consumer_checkpoints WHERE consumer=?",(consumer,)).fetchone()
            if current and current[0]==snapshot_id:return False
            conn.execute("INSERT INTO m2d_consumer_checkpoints VALUES(?,?,?) ON CONFLICT(consumer) DO UPDATE SET snapshot_id=excluded.snapshot_id,updated_at=excluded.updated_at",(consumer,snapshot_id,now()))
            return True

    def summary(self):
        with self.db.transaction() as conn:
            readiness={row[0]:row[1] for row in conn.execute("SELECT readiness,count(1) FROM job_operational_state GROUP BY readiness")};tasks={row[0]:row[1] for row in conn.execute("SELECT status,count(1) FROM m2d_tasks GROUP BY status")};distinct=conn.execute("SELECT count(DISTINCT job_key) FROM job_observations").fetchone()[0];observations=conn.execute("SELECT count(1) FROM job_observations").fetchone()[0]
        return {"coverage":self.coverage(),"readiness":readiness,"tasks":tasks,"distinct_jobs":distinct,"observations":observations,"status":"PARTIAL" if any(s["stream"]!="PIPELINE" and s["coverage_status"] in {"UNATTEMPTED","PARTIALLY_SEARCHED","ACCESS_BLOCKED"} for s in self.sources()) else "PASS"}

class GmailExportAdapter:
    VACANCY=re.compile(r"(?im)^\s*(?:job|role)\s*:\s*(?P<title>[^\r\n]+)\s*$[\s\S]*?^\s*company\s*:\s*(?P<company>[^\r\n]+)\s*$[\s\S]*?^\s*(?:url|link)\s*:\s*(?P<url>https?://\S+)")
    ANCHOR=re.compile(r'(?is)<a\b[^>]*?href=["\'](?P<url>https?://[^"\']+)["\'][^>]*>(?P<title>.*?)</a>')
    SPECIFIC_JOB=re.compile(r"(?i)(job-boards\.greenhouse\.io/[^/]+/jobs/\d+|boards\.greenhouse\.io/[^/]+/jobs/\d+|jobs\.lever\.co/[^/]+/[0-9a-f-]{20,}|linkedin\.com/(?:comm/)?jobs/view/\d+|foundit\.in/job/\d+|indeed\.[^/]+/viewjob)")
    @classmethod
    def _specific_url(cls,value):
        try:
            if not isinstance(value,str) or len(value)>2000:return None
            value=html.unescape(value)
            for _ in range(3):
                parsed=urlsplit(value)
                if parsed.scheme!="https" or parsed.username or parsed.password or parsed.port not in {None,443}:return None
                host=(parsed.hostname or "").lower().removeprefix("www.")
                query=dict(parse_qsl(parsed.query))
                wrapped=query.get("return_url") if host in {"foundit.in","foundit.co.in"} else query.get("url") if host in {"google.com","linkedin.com"} else None
                if not wrapped:break
                value=wrapped
            else:return None
            path=parsed.path.rstrip("/");identity_query={}
            patterns={
                "job-boards.greenhouse.io":r"/[^/]+/jobs/\d+",
                "boards.greenhouse.io":r"/[^/]+/jobs/\d+",
                "jobs.lever.co":r"/[^/]+/[0-9a-f-]{20,}",
                "linkedin.com":r"/(?:comm/)?jobs/view/(?:[^/]*-)?\d+",
                "foundit.in":r"/job/(?:[^/]*-)?\d+",
                "naukri.com":r"/job-listings-[^/]+-\d{8,}",
                "hirist.tech":r"/j/[^/]+-\d+(?:\.html)?",
                "wellfound.com":r"/jobs/\d+(?:-[^/]+)?",
                "jobs.smartrecruiters.com":r"/[^/]+/\d+(?:-[^/]+)?",
            }
            valid=host in patterns and re.fullmatch(patterns[host],path,re.I)
            if host in {"indeed.com","in.indeed.com","indeed.co.in"} and path=="/viewjob":
                job_id=query.get("jk","")
                valid=bool(re.fullmatch(r"[a-zA-Z0-9_-]{6,100}",job_id));identity_query={"jk":job_id}
            if host in {"glassdoor.com","glassdoor.co.in"} and path.startswith("/job-listing/"):
                job_id=query.get("jl","")
                valid=bool(re.fullmatch(r"\d+",job_id));identity_query={"jl":job_id}
            if not valid:return None
            return urlunsplit(("https",parsed.netloc.lower(),path,urlencode(identity_query),""))
        except (ValueError,TypeError):return None
    def __init__(self,engine:M2DEngine,resolver=None):
        from .alert_redirects import CachedAlertResolver
        self.engine=engine;self.resolver=resolver if resolver is not None else CachedAlertResolver(engine.db)
    def ingest(self,messages:list[EmailExportMessage],*,import_id=None,limit=100,interval_end=None,reprocess=False):
        import_id=import_id or uuid.uuid4().hex;accepted=[];skipped=0
        upper=datetime.fromisoformat(interval_end.replace("Z","+00:00")) if interval_end else datetime.max.replace(tzinfo=timezone.utc)
        for message in messages[:limit]:
            received=datetime.fromisoformat(message.received_at.replace("Z","+00:00"))
            if message.mailbox!="received" or received>upper:skipped+=1;continue
            from .alert_extraction import PARSER_VERSION
            with self.engine.db.transaction() as conn:
                version_known=conn.execute('SELECT 1 FROM email_extractions WHERE message_id=? AND parser_version=?',(message.message_id,PARSER_VERSION)).fetchone()
            if version_known and not reprocess:skipped+=1;continue
            message_reprocess=reprocess or not version_known
            combined=message.subject+" "+message.body
            from .priority_queue import record_message
            message_order=record_message(self.engine.db,message)
            marketing=bool(re.search(r"(?i)\bcourse\b|webinar|profile views?|career advice|social notification",message.subject))
            structured=[] if marketing else [m.groupdict() for m in self.VACANCY.finditer(message.body)]
            from .alert_extraction import extract_alert,PARSER_VERSION
            parsed=extract_alert(message,self.resolver)
            linked=[v.model_dump() for v in parsed['vacancies']]
            vacancies=structured+linked
            if marketing:classification="MARKETING"
            elif vacancies:classification="VACANCY"
            elif re.search(r"(?i)interview|schedule a call|interview availability",combined):classification="INTERVIEW"
            elif re.search(r"(?i)assessment|screening|coding test|take-home",combined):classification="SCREENING_REQUEST"
            elif re.search(r"(?i)application (?:was )?received|application submitted|thank you for applying|application acknowledgement",combined):classification="APPLICATION_ACKNOWLEDGEMENT"
            elif re.search(r"(?i)recruiter|talent acquisition|hiring for|job opportunity",combined):classification="RECRUITER_FOLLOW_UP"
            else:classification="NO_SPECIFIC_VACANCY"
            with self.engine.db.transaction() as conn:
                conn.execute('INSERT OR IGNORE INTO email_message_metadata VALUES(?,?,?,?)',(message.message_id,message.sender or message.sender_domain,message.subject,message.received_at))
                existing=conn.execute("SELECT 1 FROM gmail_intake WHERE message_id=?",(message.message_id,)).fetchone()
                if existing and not message_reprocess:skipped+=1;continue
                if existing:
                    conn.execute("UPDATE gmail_intake SET classification=?,vacancy_count=? WHERE message_id=?",(classification,len(vacancies),message.message_id))
                else:conn.execute("INSERT INTO gmail_intake VALUES(?,?,?,?,?,?,?,?,?)",(message.message_id,message.thread_id,message.received_at,json.dumps(message.labels),classification,len(vacancies),import_id,message.cursor,now()))
            for index,raw_values in enumerate(vacancies):
                if message_reprocess:
                    with self.engine.db.transaction() as conn:
                        known=conn.execute("SELECT 1 FROM job_observations WHERE stream='GMAIL' AND canonical_url=? AND json_extract(evidence,'$.message_id')=?",(canonical_url(raw_values['url']),message.message_id)).fetchone()
                    if known:continue
                values={k:clean(raw_values.get(k) or '') for k in ('url','company','title','location')};job_key=self.engine.observe(stream="GMAIL",source_id="gmail",provider_id=f"{message.message_id}:{index}",url=values["url"],company=values["company"],title=values["title"],location=values['location'],email_received_at=message.received_at,evidence={"message_id":message.message_id,"received_at":message.received_at,"publication_date":None,"company_inferred_from_link_host":not bool(values['company']),'parser_version':PARSER_VERSION,'original_url':raw_values.get('original_url',values['url'])});accepted.append(job_key)
            for lead in parsed['unresolved']:
                self.engine.observe(stream='GMAIL',source_id='gmail',provider_id=message.message_id+':unresolved:'+hashlib.sha256(lead.original_url.encode()).hexdigest(),url=None,company=lead.company or '',title=lead.title or '',location=lead.location or '',email_received_at=message.received_at,evidence={'message_id':message.message_id,'received_at':message.received_at,'publication_date':None,'blocker':lead.blocker,'parser_version':PARSER_VERSION,'original_url':lead.original_url})
            with self.engine.db.transaction() as conn:
                conn.execute('INSERT OR REPLACE INTO email_extractions VALUES(?,?,?,?,?,?)',(message.message_id,PARSER_VERSION,message.sender_domain or 'unknown',parsed['classification'],json.dumps({'vacancies':linked,'unresolved':[v.model_dump() for v in parsed['unresolved']],'duplicates':parsed['duplicates']}),now()))
        remaining=max(0,len(messages)-min(limit,len(messages)))
        return {"import_id":import_id,"messages_classified":min(limit,len(messages))-skipped,"vacancies":len(accepted),"skipped":skipped,"remaining":remaining,"status":"PARTIAL" if remaining else "COMPLETED","next_cursor":messages[min(limit,len(messages))-1].cursor if messages and remaining else None}

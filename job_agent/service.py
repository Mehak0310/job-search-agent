"""Transactional orchestration with metadata-only audit events."""
import hashlib
import json
from pathlib import Path

from pydantic import ValidationError

from .database import Database, now
from .matching import DeterministicMatcher
from .models import JobInput, Profile, Status, clean, key
from .candidate import CandidateProfile, SearchBackground,SKILL_DOMAINS,display_skill
from .intelligence import RecommendationEngine
from .resume_review import FactDecision,EXTRACTOR_VERSION,extract,propose
from .profile_m31 import reconciled_profile
from .classification import rank
from .freshness import WINDOWS, normalize_skills
from .freshness import discovery_priority, location_bucket, utc_timestamp
from datetime import datetime, timedelta, timezone


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def identity(job: JobInput) -> str:
    return digest([key(job.company), key(job.title), key(job.location), job.work_mode])


def content_signature(data: dict) -> str:
    fields = {name: data[name] for name in JobInput.model_fields if name not in {"source", "source_job_id", "application_url"}}
    for name in ("company", "title", "location"):
        fields[name] = key(fields[name])
    return digest(fields)


def serialize_job(row) -> dict:
    result = dict(row)
    result.pop("identity_key")
    result["skills"] = json.loads(result["skills"])
    result["match"] = json.loads(result.pop("match_detail"))
    result["is_sample"] = bool(result["is_sample"])
    result["discovery_detail"] = json.loads(result["discovery_detail"]) if result["discovery_detail"] else None
    result["listing_kind"] = "EMAIL" if result['discovery_detail'] and result['discovery_detail'].get('evidence',{}).get('origin')=='received_alert' else "SAMPLE" if result["is_sample"] else "LIVE" if result["discovery_detail"] else "IMPORTED"
    result["submission_verified"] = False
    result["status_tracking"] = "manual"
    return result


def incomplete_alert(job):
    detail=job.get('discovery_detail')
    if isinstance(detail,str):detail=json.loads(detail)
    return bool(detail and detail.get('evidence',{}).get('metadata_only'))


class JobService:
    def __init__(self, db: Database):
        self.db = db
        self.matcher = DeterministicMatcher()
        self.recommendations = RecommendationEngine(db)
        with self.db.transaction() as conn:
            if not conn.execute("SELECT 1 FROM candidate_profiles_v2 WHERE id=1").fetchone():
                legacy=Profile.model_validate_json(conn.execute("SELECT config FROM candidate_profile WHERE id=1").fetchone()[0])
                if legacy==Profile():candidate=CandidateProfile()
                else:
                    total=legacy.experience_years if legacy.experience_years is not None else None;candidate=CandidateProfile(target_titles=legacy.target_titles,search_skills=legacy.skills,total_experience_years=total,backend_experience_years=0,preferred_locations=legacy.locations,exclusions=legacy.exclusions)
                conn.execute("INSERT INTO candidate_profiles_v2(id,version,config,updated_at) VALUES (1,1,?,?)", (candidate.model_dump_json(), now()))

    def get_candidate_profile(self) -> dict:
        with self.db.transaction() as conn:
            row=conn.execute("SELECT * FROM candidate_profiles_v2 WHERE id=1").fetchone()
        result=CandidateProfile.model_validate_json(row["config"]).model_dump(mode="json")
        result.update(resume_attached=bool(row["resume_hash"]), resume_reviewed=bool(row["resume_reviewed"]),resume_name=row["resume_name"])
        with self.db.transaction() as conn:
            pending=conn.execute("SELECT count(*) FROM candidate_fact_proposals p JOIN resume_extractions e ON e.id=p.extraction_id WHERE e.resume_hash=? AND p.status='PENDING'",(row["resume_hash"],)).fetchone()[0] if row["resume_hash"] else 0
            total=conn.execute("SELECT count(*) FROM candidate_fact_proposals p JOIN resume_extractions e ON e.id=p.extraction_id WHERE e.resume_hash=?",(row["resume_hash"],)).fetchone()[0] if row["resume_hash"] else 0
        domains={name:[{"id":skill,"display_name":display_skill(skill),"years":result["technology_years"].get(skill),"sources":result["skill_evidence"].get(skill,[])} for skill in values if skill in result["professional_skills"]] for name,values in SKILL_DOMAINS.items()}
        from .private_config import document_for_role
        manifest_path=self.db.path.parent/'documents'/'manifest.json'
        entries=json.loads(manifest_path.read_text(encoding='utf-8')).get('documents',[]) if manifest_path.is_file() else []
        resume=document_for_role(entries,'resume',self.db.path.parent)
        name=resume['canonical_name'] if resume else row['resume_name'] or ''
        result.update(resume_proposals_total=total,resume_proposals_pending=pending,skill_domains=domains,resume_display_name=name,resume_display_version=result['document_versions'].get(name))
        return result

    def apply_m31_profile(self,manifest_path:Path|None=None,local_confirmation:dict|None=None):
        manifest_path=manifest_path or self.db.path.parent/"documents"/"manifest.json"
        with self.db.transaction() as conn:
            conn.execute("BEGIN IMMEDIATE");row=conn.execute("SELECT config,version FROM candidate_profiles_v2 WHERE id=1").fetchone();before=CandidateProfile.model_validate_json(row["config"]);after,context=reconciled_profile(before,manifest_path,local_confirmation)
            before_body=before.model_dump(mode="json");after_body=after.model_dump(mode="json");before_body.pop("version",None);after_body.pop("version",None);before_hash=digest(before_body);after_hash=digest(after_body)
            if before_hash==after_hash:return {"changed":False,"version":before.version,"context":context}
            changes={name:{"before":before.model_dump(mode="json").get(name),"after":after.model_dump(mode="json").get(name)} for name in CandidateProfile.model_fields if before.model_dump(mode="json").get(name)!=after.model_dump(mode="json").get(name)}
            revision_id=digest([after.version,after_hash,"M3.1"]);conn.execute("INSERT OR IGNORE INTO candidate_profile_revisions VALUES(?,?,?,?,?,?,?,?)",(revision_id,after.version,"M3.1 user confirmation and approved-document reconciliation",before_hash,after_hash,json.dumps(changes,sort_keys=True),json.dumps({"source":"user_confirmation","documents":context["documents"]},sort_keys=True),now()))
            confirmed=set(after.professional_skills)|set(after.technology_years)
            for proposal in conn.execute("SELECT id,value,status FROM candidate_fact_proposals").fetchall():
                normalized=key(proposal["value"])
                if proposal["status"]=="PENDING" and normalized in confirmed:conn.execute("INSERT OR IGNORE INTO candidate_fact_links VALUES(?,?,?,?,?)",(proposal["id"],"USER_CONFIRMED_MATCH",normalized,json.dumps({"source":"user_confirmation","reference":"M3.1 instruction"}),now()))
            self.db.audit(conn,"M31_PROFILE_RECONCILED",{"profile_version":after.version,"changed_fields":sorted(changes),"documents":sorted(context["documents"])})
        self.save_candidate_profile(after)
        with self.db.transaction() as conn:conn.execute("UPDATE candidate_profiles_v2 SET resume_reviewed=0 WHERE id=1")
        return {"changed":True,"version":after.version,"revision_id":revision_id,"context":context}

    def record_confirmed_application_answers(self, answers: dict[str,str], reference: str, scopes=None) -> dict:
        """Persist an explicit user decision without rescoring unrelated jobs."""
        if not answers or not reference or any(not isinstance(v,str) or not v.strip() for v in answers.values()):
            raise ValueError('explicit_answer_and_reference_required')
        with self.db.transaction() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row=conn.execute('SELECT config,version FROM candidate_profiles_v2 WHERE id=1').fetchone()
            before=CandidateProfile.model_validate_json(row['config'])
            values=dict(before.approved_application_answers);provenance=dict(before.fact_provenance)
            for name,value in answers.items():
                values[name]=value
                provenance[name]=[*provenance.get(name,[]),{'source':'user_confirmation','reference':reference}]
            after=before.model_copy(update={'version':row['version']+1,'approved_application_answers':values,'fact_provenance':provenance})
            old=before.model_dump(mode='json');new=after.model_dump(mode='json')
            changes={name:{'before':old[name],'after':new[name]} for name in old if old[name]!=new[name]}
            revision=digest([after.version,digest(new),reference])
            conn.execute('INSERT INTO candidate_profile_revisions VALUES(?,?,?,?,?,?,?,?)',(revision,after.version,'Explicit application-answer confirmation',digest(old),digest(new),json.dumps(changes,sort_keys=True),json.dumps({'source':'user_confirmation','reference':reference}),now()))
            conn.execute('UPDATE candidate_profiles_v2 SET version=?,config=?,updated_at=? WHERE id=1',(after.version,after.model_dump_json(),now()))
            from .fact_memory import record
            for name,value in answers.items():
                record(conn,name,value,source=reference,version=after.version,priority=1,scope=(scopes or {}).get(name,'shared'),supersede=True)
            self.db.audit(conn,'APPLICATION_ANSWERS_CONFIRMED',{'profile_version':after.version,'fields':sorted(answers),'revision_id':revision})
        return {'version':after.version,'revision_id':revision,'fields':sorted(answers)}

    def save_candidate_profile(self, profile: CandidateProfile) -> dict:
        with self.db.transaction() as conn:
            current=conn.execute("SELECT version FROM candidate_profiles_v2 WHERE id=1").fetchone()[0]
            profile=profile.model_copy(update={"version":current+1})
            conn.execute("UPDATE candidate_profiles_v2 SET version=?,config=?,updated_at=? WHERE id=1",(profile.version,profile.model_dump_json(),now()))
            search=profile.search_profile();background=profile.search_background();rescored=0
            for row in conn.execute("SELECT * FROM jobs").fetchall():
                stored=serialize_job(row)
                if incomplete_alert(stored):continue
                job=JobInput(source="stored",**{name:stored[name] for name in JobInput.model_fields if name not in {"source","source_job_id"}})
                match=rank(job,stored["discovery_detail"]["evidence"],background,search) if stored["discovery_detail"] else self.matcher.evaluate(job,search)
                conn.execute("UPDATE jobs SET match_score=?,match_detail=?,category=?,priority=?,updated_at=? WHERE id=?",(match["score"],json.dumps(match),match.get("category",stored["category"]),match.get("priority",stored["priority"]),now(),row["id"]));rescored+=1
            self.db.audit(conn,"CANDIDATE_PROFILE_UPDATED",{"version":profile.version,"reviewed":profile.reviewed,"rescored":rescored})
        metrics=self.recommendations.refresh(profile)
        from .priority_queue import after_evidence_change
        after_evidence_change(self.db)
        return self.get_candidate_profile() | {"recommendation_metrics":metrics}

    def attach_resume(self, payload: bytes, extension: str) -> dict:
        if not payload or len(payload)>5*1024*1024 or extension not in {"pdf","docx"}:
            raise ValueError("invalid_resume")
        if extension=="pdf" and not payload.startswith(b"%PDF-") or extension=="docx" and not payload.startswith(b"PK"):
            raise ValueError("invalid_resume")
        hashed=hashlib.sha256(payload).hexdigest(); folder=self.db.path.parent/"resumes"; folder.mkdir(parents=True,exist_ok=True)
        target=folder/(hashed+"."+extension); temporary=target.with_suffix(target.suffix+".tmp"); temporary.write_bytes(payload); temporary.replace(target)
        with self.db.transaction() as conn:
            conn.execute("UPDATE candidate_profiles_v2 SET resume_name=?,resume_hash=?,resume_reviewed=0,updated_at=? WHERE id=1",("resume."+extension,hashed,now()))
            self.db.audit(conn,"RESUME_REFERENCED",{"format":extension,"bytes":len(payload)})
        return {"resume_attached":True,"resume_reviewed":False,"content_hash":hashed}

    def parse_resume(self):
        with self.db.transaction() as conn: row=conn.execute("SELECT resume_hash,resume_name FROM candidate_profiles_v2 WHERE id=1").fetchone()
        if not row or not row["resume_hash"]:raise ValueError("resume_not_attached")
        extension=Path(row["resume_name"]).suffix; path=self.db.path.parent/"resumes"/(row["resume_hash"]+extension)
        sections=extract(path); extraction_id=digest([row["resume_hash"],EXTRACTOR_VERSION]); text_path=self.db.path.parent/"resume-extractions"/(extraction_id+".txt");text_path.parent.mkdir(exist_ok=True)
        text_path.write_text("\n".join(f"[{ref}] {text}" for ref,text in sections),encoding="utf-8")
        facts=propose(sections)
        for fact in facts:fact["id"]=digest([extraction_id,fact["category"],fact["value"],fact["source_ref"]])
        with self.db.transaction() as conn:
            conn.execute("INSERT OR IGNORE INTO resume_extractions VALUES (?,?,?,?,?,?,?)",(extraction_id,row["resume_hash"],extension.lstrip('.'),EXTRACTOR_VERSION,now(),len(sections),str(text_path)))
            for fact in facts:conn.execute("INSERT OR IGNORE INTO candidate_fact_proposals VALUES (?,?,?,?,?,?, 'PENDING',NULL,?,NULL)",(fact["id"],extraction_id,fact["category"],fact["value"],fact["source_ref"],fact["confidence"],now()))
            self.db.audit(conn,"RESUME_PARSED",{"pages_or_paragraphs":len(sections),"proposals":len(facts),"extractor_version":EXTRACTOR_VERSION})
        return {"extraction_id":extraction_id,"proposals":len(facts),"review_required":True}

    def proposed_facts(self):
        with self.db.transaction() as conn:
            return [dict(r) for r in conn.execute("""SELECT p.id,p.extraction_id,p.category,p.value,p.source_ref,p.confidence,p.status,p.reviewed_value,l.link_state,l.confirmed_fact_key
                FROM candidate_fact_proposals p JOIN resume_extractions e ON e.id=p.extraction_id
                JOIN candidate_profiles_v2 c ON c.resume_hash=e.resume_hash LEFT JOIN candidate_fact_links l ON l.proposal_id=p.id WHERE c.id=1 ORDER BY p.created_at,p.id""")]

    def review_fact(self,proposal_id,decision:FactDecision):
        with self.db.transaction() as conn:
            row=conn.execute("SELECT * FROM candidate_fact_proposals WHERE id=?",(proposal_id,)).fetchone()
            if not row or row["status"]!='PENDING':return False
            value=clean(decision.reviewed_value if decision.reviewed_value is not None else row["value"])
            if decision.action=='ACCEPTED' and not value:raise ValueError("accepted_fact_empty")
            conn.execute("UPDATE candidate_fact_proposals SET status=?,reviewed_value=?,reviewed_at=? WHERE id=?",(decision.action,value if decision.action=='ACCEPTED' else None,now(),proposal_id))
            conn.execute("INSERT INTO candidate_fact_audit(proposal_id,action,details,created_at) VALUES (?,?,?,?)",(proposal_id,decision.action,json.dumps({"edited":value!=row["value"]}),now()))
            if decision.action=='ACCEPTED' and row["category"]=='SKILL_UNVERIFIED':
                profile_row=conn.execute("SELECT config,version FROM candidate_profiles_v2 WHERE id=1").fetchone();profile=CandidateProfile.model_validate_json(profile_row["config"]);skills=sorted(set(profile.project_skills+[key(value)]));profile=profile.model_copy(update={"version":profile.version+1,"project_skills":skills});conn.execute("UPDATE candidate_profiles_v2 SET version=?,config=?,updated_at=? WHERE id=1",(profile.version,profile.model_dump_json(),now()))
            pending=conn.execute("SELECT count(*) FROM candidate_fact_proposals WHERE extraction_id=? AND status='PENDING'",(row["extraction_id"],)).fetchone()[0]
            if pending==0:
                conn.execute("UPDATE candidate_profiles_v2 SET resume_reviewed=1,updated_at=? WHERE id=1 AND resume_hash=(SELECT resume_hash FROM resume_extractions WHERE id=?)",(now(),row["extraction_id"]))
        return True

    def refresh_recommendations(self, top_k=250, strategy="section"):
        raw=self.get_candidate_profile()
        profile=CandidateProfile.model_validate({name:raw[name] for name in CandidateProfile.model_fields if name in raw})
        return self.recommendations.refresh(profile,top_k,strategy)

    def list_recommendations(self, eligibility=None, role_family=None, limit=50):
        clauses=["r.gate_state<>'EXCLUDED'"]; params=[]
        if eligibility:
            clauses.append("j.eligibility_state=?");params.append(eligibility)
        if role_family:
            clauses.append("j.category=?");params.append(role_family)
        with self.db.transaction() as conn:
            rows=conn.execute("SELECT j.*,r.score recommendation_score,r.confidence recommendation_confidence,r.gate_state,r.semantic_score,r.strategy,r.breakdown,r.explanation,r.ai_state,r.model_provenance FROM job_recommendations r JOIN jobs j ON j.id=r.job_id WHERE "+" AND ".join(clauses)+" ORDER BY r.score DESC,j.id LIMIT ?",params+[limit]).fetchall()
        from .review_queue import hidden_job_ids
        hidden=hidden_job_ids(self.db)
        result=[]
        for row in rows:
            if row["id"] in hidden:continue
            item=serialize_job(row); item.update(recommendation_score=row["recommendation_score"],recommendation_confidence=row["recommendation_confidence"],gate_state=row["gate_state"],semantic_score=row["semantic_score"],ranking_strategy=row["strategy"],ranking_breakdown=json.loads(row["breakdown"]),recommendation_explanation=json.loads(row["explanation"]),ai_state=row["ai_state"],model_provenance=row["model_provenance"]); result.append(item)
        return result

    @staticmethod
    def _candidate(conn)->CandidateProfile:
        return CandidateProfile.model_validate_json(conn.execute("SELECT config FROM candidate_profiles_v2 WHERE id=1").fetchone()[0])

    @staticmethod
    def _profile(conn) -> Profile:
        return JobService._candidate(conn).search_profile()

    def get_background(self):
        with self.db.transaction() as conn:return self._candidate(conn).search_background().model_dump()

    def get_profile(self) -> dict:
        with self.db.transaction() as conn:
            return self._profile(conn).model_dump(mode="json")

    def save_profile(self, profile: Profile) -> dict:
        with self.db.transaction() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row=conn.execute("SELECT version,config FROM candidate_profiles_v2 WHERE id=1").fetchone();candidate=CandidateProfile.model_validate_json(row["config"])
            updates={"version":row["version"]+1,"target_titles":profile.target_titles,"search_skills":profile.skills,"preferred_locations":profile.locations,"exclusions":profile.exclusions}
            if profile.experience_years is not None:
                updates["total_experience_years"]=profile.experience_years;updates["backend_experience_years"]=min(candidate.backend_experience_years,profile.experience_years)
            candidate=candidate.model_copy(update=updates)
            conn.execute("UPDATE candidate_profiles_v2 SET version=?,config=?,updated_at=? WHERE id=1",(candidate.version,candidate.model_dump_json(),now()))
            conn.execute("UPDATE candidate_profile SET config=?, updated_at=? WHERE id=1", (profile.model_dump_json(), now()))
            for row in conn.execute("SELECT * FROM jobs").fetchall():
                stored = serialize_job(row)
                if incomplete_alert(stored):continue
                job = JobInput(source="stored", **{name: stored[name] for name in JobInput.model_fields if name not in {"source", "source_job_id"}})
                if stored["discovery_detail"]:
                    background = candidate.search_background()
                    match = rank(job, stored["discovery_detail"]["evidence"], background, profile)
                else:
                    match = self.matcher.evaluate(job, profile)
                conn.execute("UPDATE jobs SET match_score=?, match_detail=?, category=?, priority=?, updated_at=? WHERE id=?", (match["score"], json.dumps(match), match.get("category", stored["category"]), match.get("priority", stored["priority"]), now(), row["id"]))
            self.db.audit(conn, "PROFILE_UPDATED", {"rescored": conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]})
        return profile.model_dump(mode="json")

    def import_rows(self, rows: list) -> dict:
        report = {"total": len(rows), "created": 0, "duplicates": 0, "references_added": 0, "invalid": 0, "errors": []}
        with self.db.transaction() as conn:
            conn.execute("BEGIN IMMEDIATE")
            profile = self._profile(conn)
            for index, raw in enumerate(rows, 1):
                try:
                    job = JobInput.model_validate(raw)
                except ValidationError as error:
                    # No input values, messages, contexts or arbitrary field names.
                    fields = sorted({str(e["loc"][0]) for e in error.errors() if e["loc"] and e["loc"][0] in JobInput.model_fields})
                    self._invalid(conn, report, index, "invalid_record", fields)
                    continue
                ident = identity(job)
                source = key(job.source)
                source_key = job.source_job_id or ident
                data = job.model_dump(mode="json")
                content_hash = content_signature(data)
                reference = conn.execute("SELECT * FROM source_references WHERE source=? AND source_key=?", (source, source_key)).fetchone()
                matches = conn.execute("SELECT * FROM jobs WHERE identity_key=? OR (? IS NOT NULL AND application_url=?)", (ident, job.application_url, job.application_url)).fetchall()
                if job.application_url:
                    for row in conn.execute("SELECT j.* FROM jobs j JOIN source_references r ON j.id=r.job_id WHERE r.application_url=?", (job.application_url,)).fetchall():
                        if row["id"] not in {m["id"] for m in matches}:
                            matches.append(row)
                if reference and reference["job_id"] not in {m["id"] for m in matches}:
                    matches.append(conn.execute("SELECT * FROM jobs WHERE id=?", (reference["job_id"],)).fetchone())
                if len(matches) > 1 or (matches and matches[0]["identity_key"] != ident):
                    self._invalid(conn, report, index, "identity_conflict")
                    continue
                existing = matches[0] if matches else None
                if existing:
                    canonical = serialize_job(existing)
                    canonical_hash = content_signature(canonical)
                    if canonical_hash != content_hash:
                        self._invalid(conn, report, index, "content_conflict")
                        continue
                    job_id = existing["id"]
                    report["duplicates"] += 1
                    self.db.audit(conn, "DUPLICATE_DETECTED", {"row": index}, job_id)
                else:
                    job_id = ident
                    match = self.matcher.evaluate(job, profile)
                    timestamp = now()
                    conn.execute("""INSERT INTO jobs(id, identity_key, company, title, location, work_mode, description, skills, application_url, min_experience, max_experience, is_sample, match_score, match_detail, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
                        job_id, ident, job.company, job.title, job.location, job.work_mode, job.description, json.dumps(job.skills), job.application_url,
                        job.min_experience, job.max_experience, int(job.is_sample), match["score"], json.dumps(match), Status.NEW, timestamp, timestamp))
                    conn.execute("UPDATE jobs SET first_seen=?, last_seen=?, last_changed=? WHERE id=?", (timestamp, timestamp, timestamp, job_id))
                    conn.execute("INSERT INTO status_history(job_id, previous_status, status, created_at) VALUES (?, NULL, ?, ?)", (job_id, Status.NEW, timestamp))
                    report["created"] += 1
                if not reference:
                    conn.execute("INSERT INTO source_references(job_id, source, source_key, source_job_id, application_url, content_hash, imported_at) VALUES (?, ?, ?, ?, ?, ?, ?)", (job_id, source, source_key, job.source_job_id, job.application_url, content_hash, now()))
                    conn.execute("UPDATE source_references SET first_seen=imported_at, last_seen=imported_at, last_changed=imported_at, listing_url=application_url WHERE source=? AND source_key=?", (source, source_key))
                    report["references_added"] += 1
            self.db.audit(conn, "IMPORT_COMPLETED", {k: v for k, v in report.items() if k != "errors"})
        return report

    def _invalid(self, conn, report, index, code, fields=None):
        report["invalid"] += 1
        report["errors"].append({"row": index, "code": code, "fields": fields or []})
        self.db.audit(conn, "IMPORT_RECORD_REJECTED", {"row": index, "code": code})

    def list_jobs(self, query="", status=None, work_mode=None, min_score=0, category=None, priority=None, source=None, sort="score_desc", kind=None, eligibility=None, seniority=None, employer=None, activity=None, page=None, page_size=50, freshness=None, location_bucket=None, experience=None, skills=None, skill_mode="any", title=None, platform=None):
        clauses, params = ["match_score >= ?","COALESCE(json_extract(discovery_detail,'$.evidence.retracted'),0)=0"], [min_score]
        if source!='gmail' and kind!='EMAIL':clauses.append("COALESCE(json_extract(discovery_detail,'$.evidence.metadata_only'),0)=0")
        if query:
            clauses.append("(lower(title) LIKE ? ESCAPE '\\' OR lower(company) LIKE ? ESCAPE '\\' OR lower(location) LIKE ? ESCAPE '\\')")
            escaped = key(query).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            params.extend(["%" + escaped + "%"] * 3)
        if title:
            clauses.append("lower(title) LIKE ? ESCAPE '\\'"); params.append("%"+key(title).replace("%","\\%").replace("_","\\_")+"%")
        if status:
            clauses.append("status=?")
            params.append(status)
        if work_mode:
            clauses.append("work_mode=?")
            params.append(work_mode)
        for name, value in (("category", category), ("priority", priority)):
            if value:
                clauses.append(name + "=?")
                params.append(value)
        for name,value in (("eligibility_state",eligibility),("seniority_level",seniority),("company",employer),("activity_status",activity)):
            if value: clauses.append(name+"=?"); params.append(value)
        if source:
            clauses.append("id IN (SELECT job_id FROM source_references WHERE source=?)")
            params.append(source)
        if platform:
            clauses.append("id IN (SELECT r.job_id FROM source_references r JOIN sources s ON s.id=r.source WHERE s.platform=?)"); params.append(platform)
        if location_bucket:
            values=[v for v in location_bucket.split(",") if v]; clauses.append("location_bucket IN ("+",".join("?" for _ in values)+")"); params.extend(values)
        if freshness:
            if freshness=="unknown": clauses.append("published_at IS NULL")
            elif freshness in WINDOWS: clauses.append("published_at>=?"); params.append((datetime.now(timezone.utc)-timedelta(hours=WINDOWS[freshness])).isoformat())
        if experience:
            ranges={"0-3":(0,3),"3-5":(3,5),"5-8":(5,8),"7-10":(7,10),"10+":(10,100)}
            if experience=="unknown": clauses.append("required_experience_min IS NULL")
            else:
                low,high=ranges[experience]; clauses.append("COALESCE(required_experience_max,required_experience_min)>=? AND required_experience_min<=?"); params.extend([low,high])
        if skills:
            chosen=normalize_skills(skills.split(",")); tests=[]
            for skill in chosen:
                tests.append("EXISTS(SELECT 1 FROM json_each(required_skills) WHERE lower(value)=?)"); params.append(skill)
            clauses.append((" AND " if skill_mode=="all" else " OR ").join(tests))
        if kind:
            clauses.append({"LIVE": "discovery_detail IS NOT NULL AND is_sample=0 AND COALESCE(json_extract(discovery_detail,'$.evidence.origin'),'')<>'received_alert'", "SAMPLE": "is_sample=1", "IMPORTED": "discovery_detail IS NULL AND is_sample=0",'EMAIL':"json_extract(discovery_detail,'$.evidence.origin')='received_alert'"}[kind])
        order = {"score_desc":"match_score DESC","score_asc":"match_score ASC","last_seen":"last_seen DESC","freshness":"first_seen DESC","newest":"published_at IS NULL, published_at DESC","priority":"discovery_priority DESC","updated":"source_updated_at IS NULL, source_updated_at DESC"}[sort]
        with self.db.transaction() as conn:
            where=" WHERE "+" AND ".join(clauses); total=conn.execute("SELECT COUNT(*) FROM jobs"+where,params).fetchone()[0]
            if page is None:return [serialize_job(r) for r in conn.execute("SELECT * FROM jobs"+where+" ORDER BY "+order+", id LIMIT 1000",params)]
            rows=conn.execute("SELECT * FROM jobs"+where+" ORDER BY "+order+", id LIMIT ? OFFSET ?",params+[page_size,(page-1)*page_size])
            return {"items":self._job_cards(conn,[serialize_job(r) for r in rows]),"page":page,"page_size":page_size,"total":total,"pages":(total+page_size-1)//page_size,"has_next":page*page_size<total,"has_previous":page>1}

    def _job_cards(self,conn,jobs):
        """Attach a plain-language, evidence-scoped dashboard view to stored jobs."""
        profile=CandidateProfile.model_validate_json(conn.execute("SELECT config FROM candidate_profiles_v2 WHERE id=1").fetchone()[0])
        professional=set(profile.professional_skills)|set(profile.employment_skills)|set(profile.project_skills)
        state_labels={"PASS":"Confirmed","FAIL":"Does not meet requirement","UNKNOWN":"Needs research","UNVERIFIED":"Needs research"}
        for job in jobs:
            state=conn.execute("SELECT * FROM job_operational_state WHERE job_id=? ORDER BY (job_key=job_id) DESC,updated_at DESC",(job["id"],)).fetchone()
            job_key=state["job_key"] if state else None
            packet=conn.execute("SELECT * FROM application_packets WHERE job_id=?",(job["id"],)).fetchone()
            version=conn.execute("SELECT * FROM application_packet_versions WHERE packet_id=? AND version=?",(packet["packet_id"],packet["current_version"])).fetchone() if packet else None
            contacts=[dict(r) for r in conn.execute("SELECT name,email,role_relevance,source_url,source_message_id,verification_status FROM contact_evidence WHERE job_key=? AND verification_status='VERIFIED' ORDER BY updated_at DESC",(job_key,)).fetchall()] if job_key else []
            evidence={}
            if job_key:
                for row in conn.execute("SELECT kind,state,factual,inference,evidence_url,verified_at FROM job_evidence WHERE job_key=? ORDER BY verified_at DESC",(job_key,)).fetchall():
                    evidence.setdefault(row["kind"],dict(row))
            raw_required=job.get("required_skills") or []
            if isinstance(raw_required,str):
                try:raw_required=json.loads(raw_required)
                except json.JSONDecodeError:raw_required=[]
            required=[str(value).casefold() for value in raw_required]
            matched=[skill for skill in required if skill in professional]
            if incomplete_alert(job):
                import re
                from .classification import SKILLS
                matched=[skill for skill,pattern in SKILLS.items() if skill in professional and re.search(pattern,job.get('title') or '',re.I)]
            years=profile.technology_years
            matching_reasons=[]
            for skill in matched[:3]:
                duration=years.get(skill)
                matching_reasons.append(f"{display_skill(skill)} is listed as required; {duration:g} years are confirmed in the approved profile." if duration is not None else f"{display_skill(skill)} is listed as required and is supported by approved profile evidence.")
            if not matching_reasons:
                for reason in job.get("match",{}).get("reasons",[]):
                    if reason and "category" not in reason.casefold():matching_reasons.append(reason)
                    if len(matching_reasons)==3:break
            if not matching_reasons:matching_reasons=["The vacancy has not supplied enough structured requirements for a specific evidence match."]
            if incomplete_alert(job):matching_reasons=[f'Received alert title mentions {display_skill(skill)}; approved profile supports it. Official requirements are unverified.' for skill in matched] or ['Received alert only; official requirements and fit need verification.']
            gaps=[]
            for skill in required:
                if skill in professional:continue
                if skill=="azure" and "azure fundamentals" in professional:gaps.append("Azure is required; approved evidence covers Azure fundamentals, not expert-level Azure experience.")
                else:gaps.append(f"Required skill not found in the approved profile: {display_skill(skill)}.")
                if len(gaps)==4:break
            if not required:gaps.insert(0,"Mandatory skill requirements still need structured review.")
            blocker=(job.get('discovery_detail') or {}).get('evidence',{}).get('blocker')
            if blocker:gaps.append('Vacancy link unresolved: '+blocker.replace('_',' ')+'.')
            checks=[]
            check_specs=(("Vacancy activity","active_state",("active_vacancy","active")),("India and location eligibility","india_state",("india_eligibility","india_eligible")),("Employer headcount","headcount_state",("employer_headcount","headcount")),("Permanent direct payroll","payroll_state",("direct_permanent_payroll",)),("Mandatory requirements","verification",("mandatory_requirements",)))
            for label,column,kinds in check_specs:
                raw=state[column] if state else "UNKNOWN";item=next((evidence[kind] for kind in kinds if kind in evidence),{})
                checks.append({"label":label,"state":state_labels.get(raw,"Needs research"),"detail":item.get("factual") or item.get("inference") or "No verified evidence recorded.","evidence_url":item.get("evidence_url"),"owner":"Agent research"})
            from .requirements import assess_requirements
            assessment=assess_requirements(profile.model_dump(),job,[dict(e) for e in conn.execute('SELECT * FROM job_evidence WHERE job_key=?',(job_key,))])
            checks[-1].update(state={'PASS':'Confirmed','FAIL':'Does not meet requirement','UNKNOWN':'Needs research','CONFLICT':'Conflicting evidence'}[assessment['state']],detail=' '.join(assessment['reasons']))
            questions=[]
            if packet:
                questions=[dict(r) for r in conn.execute("""SELECT q.question,q.field_kind,a.answer,a.status AS answer_status FROM application_questions q LEFT JOIN application_answers a ON a.question_id=q.question_id AND a.version=(SELECT max(version) FROM application_answers WHERE question_id=q.question_id) WHERE q.packet_id=? ORDER BY q.created_at""",(packet["packet_id"],)).fetchall()]
            missing=json.loads(packet["missing_information"]) if packet else []
            readiness=state["readiness"] if state else "PROMISING_NEEDS_VERIFICATION"
            if assessment['state']=='FAIL':readiness='EXCLUDED'
            elif assessment['state']!='PASS' and readiness in {'FULLY_VERIFIED_APPLICATION_READY','EMAIL_DRAFT_READY'}:readiness='READY_FOR_PORTAL_REVIEW'
            fit_label="Needs verification" if incomplete_alert(job) else "Not suitable" if readiness=="EXCLUDED" or job["match_score"]<40 else "Good match" if job["match_score"]>=80 else "Worth reviewing"
            if packet:
                app_status="Application text prepared for review" if packet["status"] not in ("BLOCKED_INCOMPATIBLE",) else "Application preparation blocked"
            else:app_status="Application text not prepared"
            contact_check=evidence.get("recruiter_contact")
            if contacts and readiness=="EXCLUDED":draft_status="A hiring contact was found, but this role is ineligible; no Gmail draft can be created"
            elif contacts:
                op=conn.execute("SELECT state FROM gmail_draft_operations WHERE job_key=? ORDER BY created_at DESC LIMIT 1",(job_key,)).fetchone()
                draft_status={'SAVED':'Unsent Gmail draft saved; review and send personally','PENDING':'Gmail draft creation pending; no duplicate will be created','UNCERTAIN':'Gmail outcome uncertain; verify existing drafts before retrying'}.get(op['state'] if op else '', 'Verified recruiter; review and approve the exact draft. Live creation disabled during R2 verification.')
            elif contact_check and contact_check.get("state")=="FAIL":draft_status="No recruiter email found after stored vacancy checks \u2014 apply on company website"
            elif contact_check and contact_check.get("state")=="UNKNOWN":draft_status="Recruiter research blocked or incomplete \u2014 apply on company website"
            else:draft_status="Recruiter contact not researched \u2014 apply on company website"
            from .application_state import submission_projection
            submission=submission_projection(conn,job['id']);submission_status=submission['submission_label']
            job.update(submission)
            candidate_inputs=[q["question"] for q in questions if not q.get("answer")]
            next_action="No application action; the role fails a verified eligibility rule" if readiness=="EXCLUDED" else "Review missing candidate answers" if candidate_inputs else "Research missing employer facts" if any(c["state"]=="Needs research" for c in checks) else "Review prepared application text" if packet else "Prepare application text"
            next_owner="No action" if readiness=="EXCLUDED" else "You" if candidate_inputs else "Agent research" if any(c["state"]=="Needs research" for c in checks) else "You"
            if submission['application_outcome']!='NOT_SUBMITTED':
                app_status=submission['submission_label'];next_action='View application history; no repeat preparation';next_owner='You'
            job["card"]={"job_key":job_key,"fit_label":fit_label,"matching_skills":[display_skill(value) for value in matched],"matching_reasons":matching_reasons[:3],"gaps":gaps[:5],"employer_checks":checks,"candidate_inputs":candidate_inputs,"readiness":readiness,"application_status":app_status,"draft_status":draft_status,"draft_allowed":bool(contacts) and readiness not in {"EXCLUDED","ACCESS_BLOCKED"} and (not state or state["lifecycle"]!="CLOSED"),"submission_status":submission_status,"next_action":next_action,"next_action_owner":next_owner,"packet_id":packet["packet_id"] if packet else None,"packet_version":packet["current_version"] if packet else None,"packet_status":packet["status"] if packet else None,"missing_information":missing,"subject":version["subject"] if version else None,"email_text":version["email_text"] if version else None,"supporting_statement":version["supporting_statement"] if version else None,"questions":questions,"verified_contacts":contacts,"vacancy_url":job.get("canonical_application_url") or job.get("application_url")}
            job['card']['requirement_assessment']=assessment
            job['card'].update(submission)
            if submission['application_outcome']!='NOT_SUBMITTED':job['card']['draft_allowed']=False
            browser=conn.execute('SELECT id,state,missing,documents,updated_at FROM browser_applications WHERE job_id=? ORDER BY updated_at DESC LIMIT 1',(job['id'],)).fetchone()
            if browser:
                job['card']['browser_preparation']={**dict(browser),'missing':json.loads(browser['missing']),'documents':json.loads(browser['documents'])}
            job['card']['review_hidden']=submission['application_outcome']!='NOT_SUBMITTED' or job.get('activity_status')=='CLOSED' or 'review_queue_dismissal' in evidence
        return jobs

    def get_job(self, job_id: str) -> dict | None:
        with self.db.transaction() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                return None
            job = serialize_job(row)
            from .application_state import submission_projection
            job.update(submission_projection(conn,job_id))
            job["sources"] = [dict(r) for r in conn.execute("SELECT source, source_job_id, application_url, listing_url, imported_at, first_seen, last_seen, last_changed FROM source_references WHERE job_id=? ORDER BY id", (job_id,))]
            self._job_cards(conn,[job])
            job["history"] = [dict(r) for r in conn.execute("SELECT previous_status, status, created_at FROM status_history WHERE job_id=? ORDER BY id", (job_id,))]
            return job

    def set_status(self, job_id: str, status: Status) -> bool:
        with self.db.transaction() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                return False
            if row[0] != status:
                timestamp = now()
                conn.execute("UPDATE jobs SET status=?, updated_at=? WHERE id=?", (status, timestamp, job_id))
                conn.execute("INSERT INTO status_history(job_id, previous_status, status, created_at) VALUES (?, ?, ?, ?)", (job_id, row[0], status, timestamp))
                self.db.audit(conn, "STATUS_CHANGED", {"from": row[0], "to": status, "tracking": "manual", "submission_verified": False}, job_id)
        return True

    def audit_events(self, limit=30) -> list[dict]:
        with self.db.transaction() as conn:
            events = [dict(row) for row in conn.execute("SELECT * FROM audit_events ORDER BY id DESC LIMIT ?", (limit,))]
            for event in events:
                event["details"] = json.loads(event["details"])
            return events

    def overview(self):
        with self.db.transaction() as conn:
            row=conn.execute("SELECT COUNT(*) total,SUM(status='SHORTLISTED') shortlisted,SUM(match_score>=70) strong FROM jobs WHERE COALESCE(json_extract(discovery_detail,'$.evidence.retracted'),0)=0").fetchone()
            return dict(row)

    def backfill_v4(self):
        with self.db.transaction() as conn:
            count=0
            for row in conn.execute("SELECT * FROM jobs WHERE discovery_detail IS NOT NULL"):
                detail=json.loads(row["discovery_detail"]); evidence=detail.get("evidence",{}); match=json.loads(row["match_detail"])
                published,confidence=utc_timestamp(evidence.get("published_at")); updated,_=utc_timestamp(evidence.get("source_updated_at"))
                conn.execute("""UPDATE jobs SET published_at=COALESCE(published_at,?),source_updated_at=COALESCE(source_updated_at,?),timestamp_provenance=COALESCE(timestamp_provenance,?),timestamp_confidence=?,discovery_priority=?,location_bucket=?,required_skills=?,preferred_skills=?,required_experience_min=?,required_experience_max=?,experience_scope=? WHERE id=?""",(published,updated,evidence.get("timestamp_provenance"),confidence,discovery_priority(row["match_score"],row["eligibility_state"],published),location_bucket(row["location"],row["eligibility_state"],row["work_mode"]),json.dumps(normalize_skills(evidence.get("required",[]))),json.dumps(normalize_skills(evidence.get("preferred",[]))),evidence.get("experience",{}).get("min") if evidence.get("experience") else None,evidence.get("experience",{}).get("max") if evidence.get("experience") else None,evidence.get("experience",{}).get("scope") if evidence.get("experience") else None,row["id"]));count+=1
            return count

    def save_background(self, background: SearchBackground):
        with self.db.transaction() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("UPDATE search_background SET config=? WHERE id=1", (background.model_dump_json(),))
            candidate=self._candidate(conn).model_copy(update={"version":self._candidate(conn).version+1,"total_experience_years":background.total_years,"backend_experience_years":background.backend_years,"background_established_skills":background.established_skills,"background_developing_skills":background.developing_skills})
            conn.execute("UPDATE candidate_profiles_v2 SET version=?,config=?,updated_at=? WHERE id=1",(candidate.version,candidate.model_dump_json(),now()))
            profile = candidate.search_profile()
            count = 0
            for row in conn.execute("SELECT * FROM jobs WHERE discovery_detail IS NOT NULL"):
                stored = serialize_job(row)
                if incomplete_alert(stored):continue
                job = JobInput(source="stored", **{name: stored[name] for name in JobInput.model_fields if name not in {"source", "source_job_id"}})
                match = rank(job, stored["discovery_detail"]["evidence"], background, profile)
                conn.execute("UPDATE jobs SET match_score=?, match_detail=?, category=?, priority=?, updated_at=? WHERE id=?", (match["score"], json.dumps(match), match["category"], match["priority"], now(), stored["id"]))
                count += 1
            self.db.audit(conn, "SEARCH_BACKGROUND_UPDATED", {"rescored": count})
        return background.model_dump()

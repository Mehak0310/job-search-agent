"""Transactional orchestration with metadata-only audit events."""
import hashlib
import json
from pathlib import Path

from pydantic import ValidationError

from .database import Database, now
from .matching import DeterministicMatcher
from .models import JobInput, Profile, Status, key
from .candidate import CandidateProfile, SearchBackground
from .intelligence import RecommendationEngine
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
    result["listing_kind"] = "SAMPLE" if result["is_sample"] else "LIVE" if result["discovery_detail"] else "IMPORTED"
    result["submission_verified"] = False
    result["status_tracking"] = "manual"
    return result


class JobService:
    def __init__(self, db: Database):
        self.db = db
        self.matcher = DeterministicMatcher()
        self.recommendations = RecommendationEngine(db)
        with self.db.transaction() as conn:
            conn.execute("INSERT OR IGNORE INTO candidate_profiles_v2(id,version,config,updated_at) VALUES (1,1,?,?)", (CandidateProfile().model_dump_json(), now()))

    def get_candidate_profile(self) -> dict:
        with self.db.transaction() as conn:
            row=conn.execute("SELECT * FROM candidate_profiles_v2 WHERE id=1").fetchone()
        result=CandidateProfile.model_validate_json(row["config"]).model_dump(mode="json")
        result.update(resume_attached=bool(row["resume_hash"]), resume_reviewed=bool(row["resume_reviewed"]))
        return result

    def save_candidate_profile(self, profile: CandidateProfile) -> dict:
        with self.db.transaction() as conn:
            current=conn.execute("SELECT version FROM candidate_profiles_v2 WHERE id=1").fetchone()[0]
            profile=profile.model_copy(update={"version":current+1})
            conn.execute("UPDATE candidate_profiles_v2 SET version=?,config=?,updated_at=? WHERE id=1",(profile.version,profile.model_dump_json(),now()))
            self.db.audit(conn,"CANDIDATE_PROFILE_UPDATED",{"version":profile.version,"reviewed":profile.reviewed})
        metrics=self.recommendations.refresh(profile)
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

    def refresh_recommendations(self, top_k=250, strategy="section"):
        raw=self.get_candidate_profile(); raw.pop("resume_attached",None); raw.pop("resume_reviewed",None)
        profile=CandidateProfile.model_validate(raw)
        return self.recommendations.refresh(profile,top_k,strategy)

    def list_recommendations(self, eligibility=None, role_family=None, limit=50):
        clauses=["r.gate_state<>'EXCLUDED'"]; params=[]
        if eligibility:
            clauses.append("j.eligibility_state=?");params.append(eligibility)
        if role_family:
            clauses.append("j.category=?");params.append(role_family)
        with self.db.transaction() as conn:
            rows=conn.execute("SELECT j.*,r.score recommendation_score,r.confidence recommendation_confidence,r.gate_state,r.semantic_score,r.strategy,r.breakdown,r.explanation,r.ai_state,r.model_provenance FROM job_recommendations r JOIN jobs j ON j.id=r.job_id WHERE "+" AND ".join(clauses)+" ORDER BY r.score DESC,j.id LIMIT ?",params+[limit]).fetchall()
        result=[]
        for row in rows:
            item=serialize_job(row); item.update(recommendation_score=row["recommendation_score"],recommendation_confidence=row["recommendation_confidence"],gate_state=row["gate_state"],semantic_score=row["semantic_score"],ranking_strategy=row["strategy"],ranking_breakdown=json.loads(row["breakdown"]),recommendation_explanation=json.loads(row["explanation"]),ai_state=row["ai_state"],model_provenance=row["model_provenance"]); result.append(item)
        return result

    @staticmethod
    def _profile(conn) -> Profile:
        return Profile.model_validate_json(conn.execute("SELECT config FROM candidate_profile WHERE id=1").fetchone()[0])

    def get_profile(self) -> dict:
        with self.db.transaction() as conn:
            return self._profile(conn).model_dump(mode="json")

    def save_profile(self, profile: Profile) -> dict:
        with self.db.transaction() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("UPDATE candidate_profile SET config=?, updated_at=? WHERE id=1", (profile.model_dump_json(), now()))
            for row in conn.execute("SELECT * FROM jobs").fetchall():
                stored = serialize_job(row)
                job = JobInput(source="stored", **{name: stored[name] for name in JobInput.model_fields if name not in {"source", "source_job_id"}})
                if stored["discovery_detail"]:
                    background = SearchBackground.model_validate_json(conn.execute("SELECT config FROM search_background WHERE id=1").fetchone()[0])
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
        clauses, params = ["match_score >= ?"], [min_score]
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
            clauses.append({"LIVE": "discovery_detail IS NOT NULL AND is_sample=0", "SAMPLE": "is_sample=1", "IMPORTED": "discovery_detail IS NULL AND is_sample=0"}[kind])
        order = {"score_desc":"match_score DESC","score_asc":"match_score ASC","last_seen":"last_seen DESC","freshness":"first_seen DESC","newest":"published_at IS NULL, published_at DESC","priority":"discovery_priority DESC","updated":"source_updated_at IS NULL, source_updated_at DESC"}[sort]
        with self.db.transaction() as conn:
            where=" WHERE "+" AND ".join(clauses); total=conn.execute("SELECT COUNT(*) FROM jobs"+where,params).fetchone()[0]
            if page is None:return [serialize_job(r) for r in conn.execute("SELECT * FROM jobs"+where+" ORDER BY "+order+", id LIMIT 1000",params)]
            rows=conn.execute("SELECT * FROM jobs"+where+" ORDER BY "+order+", id LIMIT ? OFFSET ?",params+[page_size,(page-1)*page_size])
            return {"items":[serialize_job(r) for r in rows],"page":page,"page_size":page_size,"total":total,"pages":(total+page_size-1)//page_size,"has_next":page*page_size<total,"has_previous":page>1}

    def get_job(self, job_id: str) -> dict | None:
        with self.db.transaction() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                return None
            job = serialize_job(row)
            job["sources"] = [dict(r) for r in conn.execute("SELECT source, source_job_id, application_url, listing_url, imported_at, first_seen, last_seen, last_changed FROM source_references WHERE job_id=? ORDER BY id", (job_id,))]
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
            row=conn.execute("SELECT COUNT(*) total,SUM(status='SHORTLISTED') shortlisted,SUM(match_score>=70) strong FROM jobs").fetchone()
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
            profile = self._profile(conn)
            count = 0
            for row in conn.execute("SELECT * FROM jobs WHERE discovery_detail IS NOT NULL"):
                stored = serialize_job(row)
                job = JobInput(source="stored", **{name: stored[name] for name in JobInput.model_fields if name not in {"source", "source_job_id"}})
                match = rank(job, stored["discovery_detail"]["evidence"], background, profile)
                conn.execute("UPDATE jobs SET match_score=?, match_detail=?, category=?, priority=?, updated_at=? WHERE id=?", (match["score"], json.dumps(match), match["category"], match["priority"], now(), stored["id"]))
                count += 1
            self.db.audit(conn, "SEARCH_BACKGROUND_UPDATED", {"rescored": count})
        return background.model_dump()

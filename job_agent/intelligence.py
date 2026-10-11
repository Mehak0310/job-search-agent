"""Local semantic matching, hard gates and explainable hybrid ranking."""
from __future__ import annotations
import hashlib, json, math, re, threading, time
from dataclasses import dataclass
from .database import now
from .models import key

MODEL_ID = "local-hash-embedding"
MODEL_VERSION = "1"
DIMENSIONS = 192
ALIASES = {"reactjs":"react", "react.js":"react", "angularjs":"angular", "dotnet":".net", "genai":"generative-ai", "llm":"generative-ai", "llms":"generative-ai", "retrieval":"rag", "faiss":"vector-search"}
ROLE_TERMS = {"frontend":{"frontend","angular","react","typescript","javascript","ui"}, "ai_application":{"ai","generative-ai","rag","fastapi","embeddings"}, "genai_application":{"generative-ai","rag","ollama","langchain"}, "frontend_lead":{"frontend","lead","architect"}, "fullstack_ai":{"fullstack","frontend","backend","ai","generative-ai"}}
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()

def tokens(text: str) -> list[str]:
    found = re.findall(r"[a-z0-9+#.]+", key(text))
    return [ALIASES.get(word, word) for word in found if len(word) > 1]

def relevant_text(job: dict, strategy: str) -> str:
    title = job.get("title", "")
    skills = " ".join(job.get("required_skills") or job.get("skills") or [])
    description = job.get("description", "")
    lines = [line for line in description.splitlines() if not re.search(r"(?i)about (?:us|the company)|equal opportunity|privacy|benefits", line)]
    body = " ".join(lines)[:12000]
    return f"{title} {skills} {body}" if strategy == "whole" else f"{title} {title} {title} {skills} {skills} {body}"

def embed(text: str) -> list[float]:
    vector = [0.0] * DIMENSIONS
    for term in tokens(text):
        digest = hashlib.sha256(term.encode()).digest()
        index = int.from_bytes(digest[:4], "big") % DIMENSIONS
        vector[index] += 1.0 if digest[4] & 1 else -1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [round(value / norm, 8) for value in vector]

def cosine(left: list[float], right: list[float]) -> float:
    return max(0.0, min(1.0, sum(a*b for a,b in zip(left, right))))

def content_hash(text: str) -> str:
    return hashlib.sha256(" ".join(text.split()).casefold().encode()).hexdigest()

class LocalEmbeddingProvider:
    model_id = MODEL_ID
    version = MODEL_VERSION
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [embed(text) for text in texts]

def gate(job: dict, profile) -> tuple[str, list[str]]:
    reasons=[]
    if job.get("eligibility_state") == "INELIGIBLE": reasons.append("Confirmed unavailable to candidates working from India")
    if job.get("activity_status") == "CLOSED": reasons.append("Listing is closed")
    haystack=key(job.get("title","")+" "+job.get("description",""))
    for exclusion in profile.exclusions:
        if exclusion in haystack: reasons.append("Excluded condition: "+exclusion)
    category=job.get("category","OTHER")
    title=key(job.get("title",""))
    if category in {"OTHER","DATA_PYTHON_SQL"} and not re.search(r"front.?end|full.?stack|\bai\b|ai application|genai|llm",title): reasons.append("Role family is outside configured targets")
    required=job.get("required_experience_min")
    if required is not None and profile.total_experience_years is not None and required > profile.total_experience_years + 2: reasons.append("Required experience substantially exceeds verified total experience")
    return ("EXCLUDED" if reasons else "UNVERIFIED" if job.get("eligibility_state") == "UNKNOWN" else "ELIGIBLE"), reasons

def profile_text(profile, strategy: str) -> str:
    roles=[]
    for role,weight in profile.target_roles.items(): roles.extend([role.replace("_"," ")] * weight)
    employment=" ".join(profile.employment_skills)
    projects=" ".join(profile.project_skills)
    return " ".join(roles+[employment,projects]) if strategy == "whole" else " ".join(roles*2+[employment,employment,projects])

class RecommendationEngine:
    def __init__(self, db, provider=None): self.db=db; self.provider=provider or LocalEmbeddingProvider()

    def _cached(self, conn, text, strategy, metrics):
        hashed=content_hash(text); row=conn.execute("SELECT vector FROM embedding_cache WHERE content_hash=? AND model_id=? AND model_version=? AND strategy=?",(hashed,self.provider.model_id,self.provider.version,strategy)).fetchone()
        if row: metrics["cache_hits"]+=1; return json.loads(row[0]),hashed
        metrics["inference_count"]+=1; vector=self.provider.embed_batch([text])[0]
        conn.execute("INSERT OR REPLACE INTO embedding_cache VALUES (?,?,?,?,?,?)",(hashed,self.provider.model_id,self.provider.version,strategy,json.dumps(vector),now()))
        return vector,hashed

    def score(self, job, profile, strategy, conn, metrics):
        state,hard=gate(job,profile)
        if state=="EXCLUDED":
            return {"score":0.0,"confidence":"HIGH","gate_state":state,"semantic_score":None,"strategy":strategy,"breakdown":{"hard_gate":0},"explanation":{"why":[],"matched_skills":[],"missing_or_uncertain":hard,"evidence":[]},"ai_state":"not_needed","model_provenance":None}
        pv,_=self._cached(conn,profile_text(profile,strategy),strategy,metrics); text=relevant_text(job,strategy); jv,hashed=self._cached(conn,text,strategy,metrics); semantic=cosine(pv,jv)
        all_skills=set(profile.employment_skills)|set(profile.project_skills); required=set(job.get("required_skills") or []); matched=sorted(required&all_skills); missing=sorted(required-all_skills)
        role=min(1.0,(job.get("match_score",0)/100)); skill=1.0 if not required else len(matched)/len(required); location=1.0 if job.get("location_bucket","") in {"DELHI_NCR","GURUGRAM","NOIDA","GREATER_NOIDA","MOHALI","CHANDIGARH","REMOTE_INDIA"} else .5; eligible=1.0 if state=="ELIGIBLE" else .35; fresh=min(1.0,max(0.0,float(job.get("discovery_priority") or 0)/100)); source=.8 if job.get("listing_kind")=="LIVE" else .6
        parts={"role_alignment":role,"skill_match":skill,"location":location,"eligibility":eligible,"freshness":fresh,"semantic":semantic,"source_reliability":source}
        weights={"role_alignment":.22,"skill_match":.18,"location":.10,"eligibility":.18,"freshness":.08,"semantic":.18,"source_reliability":.06}
        score=round(100*sum(parts[k]*weights[k] for k in weights),2)
        evidence=[line.strip()[:240] for line in job.get("description","").splitlines() if any(s in key(line) for s in matched)][:3]
        uncertain=["India eligibility is unverified"] if state=="UNVERIFIED" else []
        uncertain += ["Potentially missing skill: "+s for s in missing]
        return {"score":score,"confidence":"MEDIUM" if state=="UNVERIFIED" or not evidence else "HIGH","gate_state":state,"semantic_score":round(semantic,4),"strategy":strategy,"breakdown":{k:round(v*100,2) for k,v in parts.items()},"explanation":{"why":["Role and skills align with the reviewed profile","Semantic comparison uses job responsibilities and requirements"],"matched_skills":matched,"missing_or_uncertain":uncertain,"evidence":evidence},"ai_state":"analyzed","model_provenance":f"{self.provider.model_id}:{self.provider.version}"}

    def refresh(self, profile, top_k=250, strategy="section", job_ids=None):
        started=time.perf_counter(); metrics={"jobs_considered":0,"jobs_scored":0,"hard_exclusions":0,"cache_hits":0,"inference_count":0,"fallback_count":0,"llm_calls":0}
        with self.db.transaction() as conn:
            query="SELECT * FROM jobs"; params=[]
            if job_ids: query += " WHERE id IN ("+",".join("?"*len(job_ids))+")"; params=list(job_ids)
            rows=conn.execute(query+" ORDER BY match_score DESC,id LIMIT ?",params+[top_k]).fetchall()
            for row in rows:
                job=dict(row); job["skills"]=json.loads(job["skills"]); job["required_skills"]=json.loads(job.get("required_skills") or "[]"); job["listing_kind"]="LIVE" if job.get("discovery_detail") else "SAMPLE" if job.get("is_sample") else "IMPORTED"; metrics["jobs_considered"]+=1
                try: result=self.score(job,profile,strategy,conn,metrics)
                except Exception: metrics["fallback_count"]+=1; state,hard=gate(job,profile); result={"score":float(job["match_score"]),"confidence":"LOW","gate_state":state,"semantic_score":None,"strategy":"deterministic_fallback","breakdown":{"legacy_match":job["match_score"]},"explanation":{"why":job.get("match_detail",{}),"matched_skills":[],"missing_or_uncertain":hard+["Embedding provider unavailable"],"evidence":[]},"ai_state":"unavailable","model_provenance":None}
                metrics["hard_exclusions"] += result["gate_state"]=="EXCLUDED"; metrics["jobs_scored"] += result["gate_state"]!="EXCLUDED"; hashed=content_hash(relevant_text(job,strategy))
                conn.execute("INSERT OR REPLACE INTO job_recommendations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",(job["id"],profile.version,hashed,result["score"],result["confidence"],result["gate_state"],result["semantic_score"],result["strategy"],json.dumps(result["breakdown"]),json.dumps(result["explanation"]),result["ai_state"],result["model_provenance"],now()))
            metrics["elapsed_seconds"]=round(time.perf_counter()-started,4); total=metrics["cache_hits"]+metrics["inference_count"]; metrics["cache_hit_rate"]=round(metrics["cache_hits"]/total,4) if total else 0
            run_id=hashlib.sha256((now()+str(metrics)).encode()).hexdigest()[:16]; stamp=now(); conn.execute("INSERT INTO recommendation_runs VALUES (?,?,?,?)",(run_id,stamp,stamp,json.dumps(metrics)))
        return metrics

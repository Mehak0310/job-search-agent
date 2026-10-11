"""Conservative evidence extraction and deterministic, explainable ranking."""
import re
from datetime import datetime, timezone
from .candidate import SearchBackground
from .discovery_models import Category
from .models import JobInput, Profile, WorkMode, key

SKILLS={"angular":r"\bangular\b","react":r"\breact(?:js|\.js)?\b","javascript":r"\bjavascript\b","typescript":r"\btypescript\b","html":r"\bhtml\b","css":r"\bcss\b","rest apis":r"\brest(?:ful)?\s+apis?\b","sap spartacus":r"\bspartacus\b",".net":r"\.net\b","c#":r"\bc#","python":r"\bpython\b","sql":r"\bsql\b","data science":r"\bdata science\b","machine learning":r"\bmachine learning\b","llm application engineering":r"\bllms?\b|large language model","rag":r"\brag\b|retrieval.augmented","langchain":r"\blangchain\b","langgraph":r"\blanggraph\b","fastapi":r"\bfastapi\b","azure":r"\bazure\b"}
INDIA=r"\bindia\b|\bbengaluru\b|\bbangalore\b|\bhyderabad\b|\bgurugram\b|\bgurgaon\b|\bpune\b|\bmumbai\b|\bchennai\b|\bdelhi\b|\bnoida\b|\bkolkata\b"
FOREIGN=r"\b(united states|usa|u\.?s\.? only|canada|toronto|new york|san francisco|north america|united kingdom|london|europe only|germany|australia|singapore)\b"

def classify(title):
    title=key(title); front=bool(re.search(r"front.?end|\bangular\b|\breact\b|\bui\b",title)); ai=bool(re.search(r"\b(ai|genai|llm|rag|agentic)\b|applied ai|artificial intelligence",title)); lead=bool(re.search(r"\b(lead|staff|principal|architect|head)\b",title))
    if front:return (Category.FRONTEND_LEADERSHIP if lead else Category.FRONTEND),("P2" if re.search(r"\b(junior|entry|sde\s+i)\b",title) else "P1")
    if re.search(r"full.?stack",title):return (Category.FULLSTACK_AI if ai else Category.OTHER),"P2"
    if ai and re.search(r"engineer|developer|architect|specialist",title):return Category.AI_GENAI,"P1"
    if "consultant" in title:return Category.CONSULTING,"P2"
    if re.search(r"back.?end|\.net|c#",title):return Category.BACKEND,"P3"
    if re.search(r"python|\bsql\b|data engineer|data scientist|data analyst",title):return Category.DATA_PYTHON_SQL,"P2"
    return Category.OTHER,"P3"

def seniority_level(title):
    for level,pattern in (("MANAGER",r"\bmanager\b"),("ARCHITECT",r"\barchitect\b"),("PRINCIPAL",r"\bprincipal\b"),("STAFF",r"\bstaff\b"),("LEAD",r"\blead\b"),("SENIOR",r"\b(senior|sr\.?|sde\s*iii)\b"),("JUNIOR",r"\b(junior|entry|associate|sde\s*i)\b"),("MID_LEVEL",r"\b(mid|intermediate|sde\s*ii)\b")):
        if re.search(pattern,key(title)):return level
    return "UNKNOWN"

def extract_requirements(description):
    required,preferred,mentioned=set(),set(),set(); section=None
    for raw in description.splitlines():
        line=key(raw)
        if re.search(r"^(requirements|qualifications|what you (?:need|bring)|minimum qualifications)\s*:?$",line):section="required"
        elif re.search(r"^(preferred|nice.to.have|bonus|preferred qualifications)\s*:?$",line):section="preferred"
        elif re.search(r"^(responsibilities|benefits|about us|what you.ll do)\s*:?$",line):section=None
        present={s for s,p in SKILLS.items() if re.search(p,line,re.I)}; mentioned.update(present)
        if re.search(r"not required|not necessary",line):continue
        if re.search(r"preferred|nice.to.have|bonus|optional",line) or section=="preferred":preferred.update(present)
        elif section=="required" or re.search(r"\b(must|required|minimum)\b",line):required.update(present)
    experience=None; pattern=r"\b(\d{1,2})(?:\s*(?:-|–|—|to)\s*(\d{1,2}))?\s*(\+)?\s*years?(?:\s+of)?(?:\s+(professional|relevant|software|engineering|backend|front.?end|python|\.net|react|angular|development))?\s+experience"
    for raw in description.splitlines():
        if re.search(r"preferred|bonus|optional",raw,re.I):continue
        found=re.search(pattern,raw,re.I)
        if found:
            scope=key(found[4] or "total"); experience={"min":int(found[1]),"max":int(found[2]) if found[2] else None,"scope":"backend" if re.search(r"backend|python|\.net",scope) else "frontend" if re.search(r"front|react|angular",scope) else "total","ambiguous":scope in {"relevant","development"}}; break
    return {"required":sorted(required),"preferred":sorted(preferred-required),"mentioned":sorted(mentioned),"experience":experience,"requirements_known":bool(required)}

def eligibility(location,mode,country=None,description=""):
    loc=key(location); combined=loc+" "+key(description)[:4000]; stamp=datetime.now(timezone.utc).isoformat()
    if country=="IN" or re.search(INDIA,loc) or re.search(r"remote (?:within|in|from) india|based in india|india remote",combined):return {"state":"ELIGIBLE","explanation":"The listing explicitly includes India.","evidence":location[:300],"confidence":"HIGH","evaluated_at":stamp}
    if (country and country!="IN") or re.search(r"(?:remote|applicants?|candidates?).{0,45}(?:only|restricted).{0,45}"+FOREIGN,combined) or (mode in {WorkMode.ONSITE,WorkMode.REMOTE} and re.search(FOREIGN,loc)):return {"state":"INELIGIBLE","explanation":"The listing explicitly limits work to a geography outside India.","evidence":location[:300],"confidence":"HIGH","evaluated_at":stamp}
    return {"state":"UNKNOWN","explanation":"The listing does not state whether work from India is permitted.","evidence":location[:300] or "No location evidence","confidence":"LOW","evaluated_at":stamp}

def india_eligibility(location,mode,country=None):return eligibility(location,mode,country)["state"]

def rank(job,evidence,background,profile):
    category,priority=classify(job.title); level=seniority_level(job.title); reasons=[f"Role category {category}, priority {priority}"]; missing=[]; dis=[]; score={"P1":30,"P2":22,"P3":10}[priority] if category!=Category.OTHER or priority=="P2" else 0
    required=set(evidence["required"]); assessed=required or set(evidence["mentioned"]); established=set(background.established_skills); developing=set(background.developing_skills)
    if assessed:
        score+=round(30*(len(assessed&established)+.5*len((assessed&developing)-established))/len(assessed))
        if assessed&established:reasons.append("Established strengths: "+", ".join(sorted(assessed&established)))
        if (assessed&developing)-established:reasons.append("Transition skills: "+", ".join(sorted((assessed&developing)-established)))
        missing += ["Required skill: "+s for s in sorted(required-established-developing)]+["Professional evidence needed for required skill: "+s for s in sorted((required&developing)-established)]
    else:missing.append("Technical requirements unknown")
    if not evidence["requirements_known"]:missing.append("Mandatory versus preferred requirements could not be reliably established")
    elig=eligibility(job.location,job.work_mode,evidence.get("country"),job.description)
    if elig["state"]=="ELIGIBLE":score+=20; reasons.append(elig["explanation"])
    elif elig["state"]=="INELIGIBLE":score-=20; dis.append(elig["explanation"])
    else:score+=3; missing.append(elig["explanation"])
    if job.work_mode in profile.work_modes and job.work_mode!=WorkMode.UNKNOWN:score+=10; reasons.append("Work mode matches preferences")
    elif job.work_mode==WorkMode.UNKNOWN:missing.append("Work mode unknown")
    else:score-=10; dis.append("Work mode is outside configured preferences")
    exp=evidence["experience"]; seniority="UNKNOWN"; relevant=background.backend_years if (exp and exp.get("scope")=="backend") or category==Category.BACKEND else background.total_years
    if exp:
        if relevant<exp["min"]:seniority="BELOW_STATED_MINIMUM";score-=15;dis.append(f"Stated minimum {exp['min']} years exceeds relevant {relevant:g} years")
        elif exp["max"] is not None and relevant>exp["max"]:seniority="REVIEW_REQUIRED";missing.append("Candidate experience exceeds stated range; review level")
        else:seniority="REVIEW_REQUIRED" if exp.get("ambiguous") else "COMPATIBLE";score+=6 if exp.get("ambiguous") else 10;reasons.append(f"Experience range fits {relevant:g} relevant years")
    else:score+=5;missing.append("Experience requirement unknown; title alone does not establish years")
    if level=="JUNIOR" and background.total_years>=5:seniority="REVIEW_REQUIRED";score-=12;missing.append("Junior scope may undershoot overall experience")
    if level in {"STAFF","PRINCIPAL","ARCHITECT","MANAGER"} and not exp:seniority="REVIEW_REQUIRED";score-=5
    if category==Category.AI_GENAI and re.search(r"\b(research|phd|scientist)\b",key(job.title)):score-=20;reasons.append("AI research specialization adjustment")
    penalty=15 if category==Category.BACKEND else 0;score-=penalty
    if penalty:reasons.append("Backend specialization adjustment: 3–4 years rather than seven")
    for exclusion in profile.exclusions:
        if exclusion in key(job.title+" "+job.description):score-=30;dis.append("Exclusion matched: "+exclusion)
    confidence="HIGH" if evidence["requirements_known"] and elig["confidence"]=="HIGH" and exp else "MEDIUM" if evidence["requirements_known"] or exp else "LOW"
    return {"score":max(0,min(100,score)),"category":category,"priority":priority,"confidence":confidence,"reasons":reasons,"missing_requirements":missing,"potential_disqualifiers":dis,"seniority_level":level,"seniority_compatibility":seniority,"location_eligibility":elig["state"],"eligibility":elig,"backend_penalty":penalty,"evidence":evidence}

"""Fail-closed clause inventory. Imported JD text never grants completeness or facts."""
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from html import unescape
from .classification import SKILLS, extract_requirements
from .eligibility import _https_url

VERSION='jd-clauses-3'

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),default=str).encode()).hexdigest()


def _timestamp(value):
    if not value:return None
    try:
        parsed=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (TypeError,ValueError):return None


def inventory(job,at=None):
    raw=job.get('description') or ''
    source_hash=hashlib.sha256(raw.encode()).hexdigest()
    detail=job.get('discovery_detail') or {}
    if isinstance(detail,str):
        try:detail=json.loads(detail)
        except ValueError:detail={}
    if not isinstance(detail,dict):detail={}
    provenance=detail.get('requirements_source') or {}
    if not isinstance(provenance,dict):provenance={}
    reviews=provenance.get('nonmandatory_reviews') or []
    if not isinstance(reviews,list):reviews=[]
    at=at or datetime.now(timezone.utc)
    if at.tzinfo is None:at=at.replace(tzinfo=timezone.utc)
    at=at.astimezone(timezone.utc);verified_at=_timestamp(provenance.get('verified_at'))
    current=verified_at is not None and at-timedelta(days=7)<=verified_at<=at
    complete=provenance.get('content_status')=='FULL' and provenance.get('description_sha256')==source_hash and _https_url(provenance.get('source_url')) and current
    issues=[]
    if not raw.strip():issues.append('Full JD content is missing; mandatory requirements cannot be established.')
    elif not complete:issues.append('Full JD completeness is unverified, stale, or missing source time for this content hash; a current complete source is required.')
    text=unescape(re.sub(r'<[^>]*>',lambda m:'\n' if re.match(r'</?(?:p|li|br|h[1-6]|div)\b',m[0],re.I) else ' ',raw))
    if re.search(r'\.{3}\s*$|…\s*$|\b(?:truncated|read more|show more|description unavailable)\b',text,re.I) or job.get('description_truncated'):
        issues.append('JD appears partial or truncated; obtain the complete vacancy before eligibility can pass.')
    section=None;clauses=[];occurrences={}
    for line in re.split(r'[\r\n]+',text):
        # Sentence boundaries preserve decimals, skill names and each original excerpt.
        for segment in re.split(r'(?<=[.!?])\s+(?=[A-Z])',line):
            excerpt=segment.strip(' \t•*-')
            if not excerpt:continue
            heading=re.match(r'^(requirements|qualifications|minimum qualifications|basic qualifications|what you (?:need|bring)|required(?: qualifications| skills)?|preferred(?: qualifications| skills)?|nice.to.have|bonus|responsibilities|benefits|about us|what you.ll do)\s*[:：]?\s*$',excerpt,re.I)
            inline=re.match(r'^(requirements|qualifications|minimum qualifications|preferred qualifications|preferred|responsibilities)\s*[:：]\s*(.+)$',excerpt,re.I)
            if heading or inline:
                h=(heading or inline)[1].casefold()
                section='PREFERRED' if re.search('preferred|nice|bonus',h) else 'INFORMATIONAL' if h in {'responsibilities','benefits','about us',"what you'll do"} else 'MANDATORY'
                if heading:continue
                excerpt=inline[2].strip()
            lower=excerpt.casefold()
            mandatory=bool(re.search(r'\b(?:must|shall|require(?:s|d)?|mandatory|minimum|need(?:s)?|have to|essential|only|prerequisite|necessary|obligatory)\b',lower))
            preferred=bool(re.search(r'\b(?:preferred|preferably|optional|bonus|nice.to.have|not required|not necessary)\b',lower))
            category='PREFERRED' if preferred and not re.search(r'\b(?:must|shall|mandatory)\b',lower) else 'MANDATORY' if mandatory else section or 'AMBIGUOUS'
            if category=='INFORMATIONAL':category='AMBIGUOUS'
            if preferred and mandatory and not re.search(r'not required|not necessary',lower):category='AMBIGUOUS'
            normalized=' '.join(lower.split());occurrences[normalized]=occurrences.get(normalized,0)+1
            identifier='clause-'+digest([normalized,occurrences[normalized]])[:24]
            # A section heading is context, never evidence that a clause is harmless.
            review=next((r for r in reviews if isinstance(r,dict) and r.get('clause_id')==identifier and r.get('source_excerpt')==excerpt and r.get('source_hash')==source_hash and r.get('classification')=='INFORMATIONAL' and r.get('reviewer') and r.get('evidence_ref')),None)
            if complete and review and category=='AMBIGUOUS' and not mandatory:category='INFORMATIONAL'
            skills=[s for s,p in SKILLS.items() if re.search(p,lower,re.I)]
            parsed=extract_requirements(excerpt);experience=parsed.get('experience')
            if re.search(r'\d+\.\d+\s*(?:\+)?\s*years?',lower):experience=None
            remainder=lower
            for pattern in SKILLS.values():remainder=re.sub(pattern,' ',remainder,flags=re.I)
            # Only an explicit, narrow grammar can fully map a mandatory clause.
            remainder=re.sub(r'\b\d+(?:\.\d+)?\s*(?:\+|[-–—]\s*\d+)?\s*years?\b',' ',remainder)
            remainder=re.sub(r'\b(?:must|have|has|a|an|the|and|or|with|of|in|on|are|is|be|required|require|requires|minimum|at|least|professional|total|overall|software|engineering|backend|frontend|front|end|development|relevant|experience|experienced|knowledge|proficiency|proficient|skills?|strong|solid|working|hands|expertise|essential|mandatory|demonstrated|proven|you|need|to|plus)\b',' ',remainder)
            unsupported=bool(re.sub(r'[\W_]+','',remainder)) or not (skills or experience)
            if ' or ' in lower and category=='MANDATORY':unsupported=True
            durations=re.findall(r'\b\d+(?:\.\d+)?\s*(?:\+|[-\u2013\u2014]\s*\d+)?\s*years?\b',lower)
            if durations and (not experience or len(durations)>1):unsupported=True
            if skills and experience:
                experience={**experience,'scope':'skill:'+','.join(skills),'ambiguous':True}
            clauses.append({'id':identifier,'excerpt':excerpt,'classification':category,'potentially_mandatory':category in {'MANDATORY','AMBIGUOUS'},'mapping':'UNSUPPORTED' if unsupported else 'SUPPORTED','skills':skills,'experience':experience,'source_hash':source_hash,'extractor_version':VERSION,'classification_provenance':review if complete and category=='INFORMATIONAL' else {'basis':'JD wording/section; no nonmandatory exemption'}})
    if not any(c['classification']=='MANDATORY' for c in clauses):issues.append('No mandatory clause inventory was established; absence is not proof of no requirements.')
    return {'clauses':clauses,'completeness_issues':issues,'source_hash':source_hash,'extractor_version':VERSION,'source_provenance':provenance}

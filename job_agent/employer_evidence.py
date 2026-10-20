"""Reusable scoped employer research with an explicit freshness limit."""
import json
from datetime import datetime,timedelta,timezone
from pathlib import Path


def cached_employer(path: Path, entity: str, scope: str, at=None):
    """Never transfer parent-group research to a subsidiary or different scope."""
    at=at or datetime.now(timezone.utc)
    if not path.is_file():return None
    data=json.loads(path.read_text(encoding='utf-8'))
    if data.get('entity')!=entity or data.get('scope')!=scope:return None
    if datetime.fromisoformat(data['expires_at'])<=at:return None
    return data


def cache_employer(path: Path, *, entity: str, scope: str, headcount: int, as_of: str, url: str, at=None):
    at=at or datetime.now(timezone.utc)
    data={'entity':entity,'scope':scope,'headcount':headcount,'as_of':as_of,'evidence_url':url,
          'checked_at':at.isoformat(),'expires_at':(at+timedelta(days=90)).isoformat()}
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data,indent=2),encoding='utf-8')
    return data


def reuse_large_employer_check(db,job,*,at=None):
    """Reuse recent exact-company global size evidence, never a subsidiary claim."""
    if job.get('headcount_state')!='UNKNOWN':return job
    from .eligibility import EMPLOYER_EVIDENCE_DAYS, _headcount_verdict, _https_url, _timestamp
    at=at or datetime.now(timezone.utc)
    with db.transaction() as conn:
        rows=conn.execute("SELECT e.factual,e.evidence_url,e.verified_at,e.state FROM job_evidence e JOIN job_operational_state s ON s.job_key=e.job_key JOIN jobs j ON j.id=s.job_id WHERE lower(j.company)=lower(?) AND e.kind='headcount' AND e.state IN ('PASS','FAIL') ORDER BY e.verified_at DESC",(job['company'],)).fetchall()
    threshold=500 if job.get('work_mode')=='remote' else 1000
    for evidence in rows:
        body=evidence['factual'] or ''
        verified_at=_timestamp(evidence['verified_at'])
        if (
            'global' not in body.casefold()
            or not verified_at
            or not at-timedelta(days=EMPLOYER_EVIDENCE_DAYS)<=verified_at<=at
            or not _https_url(evidence['evidence_url'])
            or evidence['state']!='PASS'
            or _headcount_verdict(body,threshold)!='PASS'
        ):
            continue
        from .m2d import M2DEngine
        from .database import now
        M2DEngine(db).record_evidence(job['job_key'],'headcount','PASS',factual=body,evidence_url=evidence['evidence_url'],verified_at=evidence['verified_at'])
        missing=[v for v in json.loads(job['missing_facts'] or '[]') if v!='headcount']
        with db.transaction() as conn:conn.execute("UPDATE job_operational_state SET headcount_state='PASS',missing_facts=?,updated_at=? WHERE job_key=?",(json.dumps(missing),now(),job['job_key']))
        return {**job,'headcount_state':'PASS','missing_facts':json.dumps(missing)}
    return job

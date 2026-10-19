"""Materialise received-alert evidence in the existing canonical opportunity store."""
import json
from .database import now
from .m2d import canonical_url
from .models import Status


def reconcile_parser_observations(db):
    """Retract superseded parser-only false positives without deleting provenance/history."""
    from .alert_extraction import PARSER_VERSION
    retracted=0
    with db.transaction() as conn:
        for row in conn.execute('SELECT message_id,report FROM email_extractions WHERE parser_version=?',(PARSER_VERSION,)).fetchall():
            parsed=json.loads(row['report']);urls={canonical_url(v['url']) for v in parsed['vacancies']};pending={v['original_url'] for v in parsed['unresolved']}
            observations=conn.execute("SELECT * FROM job_observations WHERE stream='GMAIL' AND json_extract(evidence,'$.message_id')=? AND json_extract(evidence,'$.parser_version')=?",(row['message_id'],PARSER_VERSION)).fetchall()
            for obs in observations:
                evidence=json.loads(obs['evidence'])
                valid=obs['canonical_url'] in urls if obs['canonical_url'] else evidence.get('original_url') in pending
                if valid or evidence.get('parser_retracted'):continue
                evidence['parser_retracted']=True;conn.execute('UPDATE job_observations SET evidence=? WHERE observation_id=?',(json.dumps(evidence),obs['observation_id']))
                job=conn.execute("SELECT j.* FROM jobs j JOIN job_operational_state s ON s.job_id=j.id WHERE s.job_key=? AND j.status='NEW'",(obs['job_key'],)).fetchone()
                if job:
                    detail=json.loads(job['discovery_detail'] or '{}')
                    if detail.get('evidence',{}).get('metadata_only'):
                        detail['evidence']['retracted']=True;conn.execute('UPDATE jobs SET discovery_detail=? WHERE id=?',(json.dumps(detail),job['id']))
                        conn.execute("UPDATE job_operational_state SET readiness='EXCLUDED',exclusion_reason='Parser correction: generic link, not a named vacancy' WHERE job_id=?",(job['id'],));retracted+=1
        if retracted:db.audit(conn,'ALERT_PARSER_FALSE_POSITIVES_RETRACTED',{'count':retracted})
    return retracted


def sync_email_opportunities(db):
    reconcile_parser_observations(db)
    result={'created':0,'linked_existing':0,'unchanged':0}
    with db.transaction() as conn:
        conn.execute('BEGIN IMMEDIATE')
        existing={}
        for row in conn.execute('SELECT id,application_url,listing_url,canonical_application_url FROM jobs'):
            for url in (row['application_url'],row['listing_url'],row['canonical_application_url']):
                if url:existing.setdefault(canonical_url(url),set()).add(row['id'])
        groups={}
        for row in conn.execute("SELECT * FROM job_observations WHERE stream='GMAIL' ORDER BY observed_at,observation_id"):
            if json.loads(row['evidence']).get('parser_retracted'):continue
            groups.setdefault(row['job_key'],[]).append(row)
        for job_key,observations in groups.items():
            evidence=[json.loads(o['evidence']) for o in observations];url=observations[0]['canonical_url']
            matches=existing.get(canonical_url(url),set()) if url else set()
            state=conn.execute('SELECT job_id FROM job_operational_state WHERE job_key=?',(job_key,)).fetchone()
            if state and state['job_id']:
                job=conn.execute('SELECT discovery_detail FROM jobs WHERE id=?',(state['job_id'],)).fetchone()
                detail=json.loads(job['discovery_detail'] or '{}') if job else {}
                if detail.get('evidence',{}).get('metadata_only'):
                    detail['evidence']['blocker']=json.loads(observations[-1]['evidence']).get('blocker')
                    detail['evidence']['source_message_refs']=sorted({e.get('message_id') for e in evidence if e.get('message_id')})
                    conn.execute('UPDATE jobs SET discovery_detail=?,last_seen=MAX(last_seen,?) WHERE id=?',(json.dumps(detail),max(o['observed_at'] for o in observations),state['job_id']))
                result['unchanged']+=1;job_id=state['job_id']
            elif len(matches)==1:
                job_id=next(iter(matches));result['linked_existing']+=1
            else:
                first=evidence[0];company=next((e.get('company') for e in evidence if e.get('company') and not e.get('company_inferred_from_link_host')),None)
                title=next((e.get('title') for e in evidence if e.get('title') and e.get('title') not in {'View job','View Job','Apply','Apply now'}),None)
                location=next((e.get('location') for e in evidence if e.get('location')),None)
                timestamp=min(o['observed_at'] for o in observations);latest=max(o['observed_at'] for o in observations);job_id=job_key
                detail={'owner_source':'gmail','evidence':{'origin':'received_alert','metadata_only':True,'blocker':'canonical_identity_ambiguous' if len(matches)>1 else first.get('blocker'),'required':[],'preferred':[],'mentioned':[],'published_at':None,'company_unverified':True,'source_message_refs':sorted({e.get('message_id') for e in evidence if e.get('message_id')})}}
                match={'score':0,'reasons':['Received alert only; official requirements and fit need verification.'],'missing_requirements':['Official job description, employer and employment terms need agent research.'],'potential_disqualifiers':[],'confidence':'LOW','evidence':detail['evidence']}
                conn.execute("""INSERT INTO jobs(id,identity_key,company,title,location,work_mode,description,skills,application_url,is_sample,match_score,match_detail,status,created_at,updated_at,first_seen,last_seen,last_changed,listing_url,canonical_application_url,discovery_detail,activity_status,eligibility_state)
                    VALUES(?,?,?,?,?,'unknown','','[]',?,0,0,?,'NEW',?,?,?,?,?,?,?,?,'UNKNOWN','UNKNOWN')""",
                    (job_id,'alert:'+job_key,company,title,location,None if len(matches)>1 else url,json.dumps(match),timestamp,timestamp,timestamp,latest,timestamp,url,url,json.dumps(detail)))
                conn.execute('INSERT INTO status_history(job_id,previous_status,status,created_at) VALUES(?,NULL,?,?)',(job_id,Status.NEW,timestamp));result['created']+=1
                if url:existing.setdefault(canonical_url(url),set()).add(job_id)
            conn.execute('UPDATE job_operational_state SET job_id=? WHERE job_key=? AND job_id IS NULL',(job_id,job_key))
            for observation,e in zip(observations,evidence):
                provider_id=e.get('message_id') or observation['provider_id']
                conn.execute("""INSERT OR IGNORE INTO source_references(job_id,source,source_key,source_job_id,application_url,content_hash,imported_at,first_seen,last_seen,last_changed,listing_url)
                    VALUES(?,'gmail',?,?,?,?,?,?,?,?,?)""",(job_id,provider_id+':'+job_key,provider_id,url,job_key,observation['observed_at'],observation['observed_at'],observation['observed_at'],observation['observed_at'],url))
        db.audit(conn,'EMAIL_OPPORTUNITIES_SYNCED',result)
    return result

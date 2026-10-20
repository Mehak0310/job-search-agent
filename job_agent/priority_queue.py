"""Persisted verified application priority; active work is never reprioritized."""
import json,re
from datetime import datetime,timezone
from urllib.parse import urlsplit
from .database import now
from .runtime_policy import digest

VERSION='verified-priority-1'


def schema(conn):
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS application_priority(
      job_id TEXT PRIMARY KEY REFERENCES jobs(id),identity TEXT NOT NULL,state TEXT NOT NULL,
      fit REAL NOT NULL,recruiter_tier INTEGER NOT NULL DEFAULT 0,deadline TEXT,
      freshness TEXT,source TEXT NOT NULL,reason TEXT NOT NULL,eligibility TEXT NOT NULL,
      evidence_hash TEXT NOT NULL,queued_at TEXT NOT NULL,last_processed TEXT,
      skips INTEGER NOT NULL DEFAULT 0,attempts INTEGER NOT NULL DEFAULT 0,
      batch_id TEXT,reserved_order INTEGER,updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS message_priority(message_id TEXT PRIMARY KEY,
      category TEXT NOT NULL,tier INTEGER NOT NULL,deadline TEXT,reason TEXT NOT NULL,version TEXT NOT NULL);
    ''')


def classify_message(message):
    subject=message.subject or '';body=message.body or '';text=subject+' '+body
    sender=(message.sender or message.sender_domain or '').casefold()
    automatic=bool(re.search(r'job alerts?|jobs? (?:for you|matching)|recommended jobs|new jobs|unsubscribe|view all jobs|manage.*alerts',text,re.I) or re.search(r'no.?reply|notifications?@|jobalert|naukri|indeed|glassdoor|jobs-listings|linkedin.*jobs',sender))
    if automatic:return {'category':'AUTOMATED_JOB_ALERT','tier':0,'deadline':None,'reason':'Automated alert; not a recruiter conversation','version':VERSION}
    genuine=bool((re.search(r'\b(?:interview|screening|assessment|availability|recruiter|talent acquisition|hiring team)\b',text,re.I) or re.search(r'recruit|talent|hiring',sender)) and re.search(r'\b(?:reply|respond|please|your availability|you available|complete|submit.*assessment)\b',text,re.I))
    deadline=None
    found=re.search(r'(?:deadline|due|respond by|reply by|complete by)\s*[:\-]?\s*(\d{4}-\d{2}-\d{2})(?:[ T](\d{2}:\d{2}))?',text,re.I)
    if found:
        try:deadline=datetime.fromisoformat(found[1]+'T'+(found[2] or '23:59')+':00+00:00').isoformat()
        except ValueError:pass
    if genuine:
        category='INTERVIEW_REQUEST' if re.search(r'interview|availability',text,re.I) else 'SCREENING_QUESTIONS' if re.search(r'screening|assessment|questions',text,re.I) else 'DIRECT_RECRUITER_ACTION'
        urgent=bool(re.search(r'urgent|today|asap|within 24 hours',text,re.I))
        if deadline:
            reference=datetime.fromisoformat(message.received_at.replace('Z','+00:00'))
            urgent=urgent or (datetime.fromisoformat(deadline)-reference).total_seconds()<=172800
        return {'category':category,'tier':3 if urgent else 2,'deadline':deadline,'reason':category.replace('_',' ').title()+('; urgent or deadline within 48h' if urgent else '; explicit recipient action requested'),'version':VERSION}
    followup=bool(re.search(r'recruiter|talent acquisition|following up|hiring for',text,re.I))
    return {'category':'RECRUITER_FOLLOW_UP' if followup else 'OTHER_RECEIVED_MESSAGE','tier':1 if followup else 0,'deadline':None,'reason':'Recruiter follow-up; no direct action established' if followup else 'No verified recruiter action','version':VERSION}


def record_message(db,message):
    item=classify_message(message)
    with db.transaction() as conn:conn.execute('INSERT OR REPLACE INTO message_priority VALUES(?,?,?,?,?,?)',(message.message_id,item['category'],item['tier'],item['deadline'],item['reason'],VERSION))
    return item


def after_evidence_change(db):
    with db.transaction() as conn:initialized=conn.execute('SELECT 1 FROM application_priority LIMIT 1').fetchone()
    if initialized:refresh(db)


def refresh(db):
    from .requirements import assess_requirements
    from .eligibility import assess_hard_eligibility
    from .browser_store import vacancy_identity,ats_for
    warm_messages(db)
    from .review_queue import hidden_job_ids
    hidden=hidden_job_ids(db)
    with db.transaction() as conn:
        for q in conn.execute("SELECT * FROM application_priority WHERE state='RESERVED'").fetchall():
            work=conn.execute('SELECT state FROM browser_workflows WHERE batch_id=? ORDER BY created_at DESC LIMIT 1',(q['batch_id'],)).fetchone()
            if work and work['state'] in {'ERROR','INTERRUPTED','COMPLETED'}:
                conn.execute("UPDATE application_priority SET state='REVIEW_REQUIRED',reason='Prior worker ended; inspect existing progress, never replay uncertain writes.',updated_at=? WHERE job_id=?",(now(),q['job_id']))
            elif not work and (datetime.now(timezone.utc)-datetime.fromisoformat(q['updated_at'])).total_seconds()>120:
                conn.execute("UPDATE application_priority SET state='REVIEW_REQUIRED',reason='Reservation has no live worker; inspect progress before any retry.',updated_at=? WHERE job_id=?",(now(),q['job_id']))
        profile=json.loads(conn.execute('SELECT config FROM candidate_profiles_v2 WHERE id=1').fetchone()[0])
        rows=[dict(r) for r in conn.execute('SELECT j.*,s.job_key,s.active_state,s.india_state,s.headcount_state,s.payroll_state,s.lifecycle,s.readiness FROM jobs j JOIN job_operational_state s ON s.job_id=j.id ORDER BY j.match_score DESC,j.id')]
        evidence={}
        for e in conn.execute('SELECT * FROM job_evidence'):evidence.setdefault(e['job_key'],[]).append(dict(e))
        messages={r['message_id']:dict(r) for r in conn.execute('SELECT * FROM message_priority')}
        contacts={}
        for c in conn.execute("SELECT * FROM contact_evidence WHERE verification_status='VERIFIED' AND source_message_id IS NOT NULL"):
            if c['source_message_id'] in messages:contacts.setdefault(c['job_key'],[]).append(messages[c['source_message_id']])
        existing={r['job_id']:dict(r) for r in conn.execute('SELECT * FROM application_priority')}
        preparations={r['job_id']:dict(r) for r in conn.execute('SELECT * FROM browser_applications')}
        prepared_identities={r['identity'] for r in preparations.values()}
        source_rows={}
        for ref in conn.execute('SELECT job_id,source,listing_url,application_url,last_seen,imported_at FROM source_references ORDER BY id'):
            source_rows.setdefault(ref['job_id'],[]).append(dict(ref))
        sources={job_id:refs[0]['source'] for job_id,refs in source_rows.items()}
        submitted={r[0] for r in conn.execute("SELECT job_id FROM status_history WHERE status='SUBMITTED' UNION SELECT job_id FROM browser_applications WHERE application_outcome IN ('USER_REPORTED_SUBMITTED','SUBMISSION_CONFIRMED') OR state IN ('USER_REPORTED_SUBMITTED','SUBMISSION_CONFIRMED') UNION SELECT a.job_id FROM browser_events e JOIN browser_applications a ON a.id=e.application_id WHERE json_extract(e.details,'$.state') IN ('USER_REPORTED_SUBMITTED','SUBMISSION_CONFIRMED')")}
        submitted_identities={vacancy_identity(j) for j in rows if (j['id'] in submitted or j['status']=='SUBMITTED') and j['company'] and ats_for(j['application_url'] or '')}
        closed_identities={vacancy_identity(j) for j in rows if (j['activity_status']=='CLOSED' or j['lifecycle']=='CLOSED' or j['status']=='NOT_RELEVANT') and j['company'] and ats_for(j['application_url'] or '')}
        decisions=[];identities=set()
        for job in rows:
            prior=existing.get(job['id']);app=preparations.get(job['id']);identity=vacancy_identity(job)
            if prior and prior['state']=='RESERVED':continue
            hard=assess_hard_eligibility(job,evidence.get(job['job_key'],[]),source_rows.get(job['id'],[]))
            assessment=assess_requirements(profile,job,evidence.get(job['job_key'],[])) if hard['state']=='PASS' else {'state':'UNKNOWN','reasons':['Mandatory requirements cannot pass while hard eligibility gates are unresolved.']}
            if job['activity_status']=='CLOSED' or job['lifecycle']=='CLOSED' or job['status']=='NOT_RELEVANT' or identity in closed_identities:
                hard['state']='FAIL';hard['reasons']=['Vacancy is closed, removed, or aliases a closed requisition.']
            states=[hard['state'],assessment['state']]
            eligibility='FAIL' if 'FAIL' in states or job['readiness']=='EXCLUDED' else 'CONFLICT' if 'CONFLICT' in states else 'PASS' if all(value=='PASS' for value in states) else 'UNKNOWN'
            if eligibility=='PASS' and not (job['company'] and job['title'] and job['application_url']):eligibility='UNKNOWN'
            state='PENDING' if eligibility=='PASS' else 'EXCLUDED' if eligibility=='FAIL' else 'VERIFICATION'
            blockers=hard['reasons'] if hard['state']!='PASS' else assessment.get('reasons',[])
            if eligibility=='FAIL' and not blockers: blockers=['Vacancy is closed, removed, or explicitly excluded.']
            reason='Verified fit descending; deadline, freshness and stable job ID break ties.' if state=='PENDING' else 'Verification required: '+'; '.join(blockers or [assessment['state']])
            if job['id'] in submitted or job['status']=='SUBMITTED' or identity in submitted_identities:state='SUBMITTED'
            elif job['id'] in hidden:state='SUPPRESSED';reason='Unavailable or removed from active review; history retained.'
            elif (app or identity in prepared_identities) and eligibility=='PASS':state='REVIEW_REQUIRED' if prior and prior['state']=='REVIEW_REQUIRED' else 'EXISTING_PROGRESS'
            elif job['status'] in {'INTERVIEW','REJECTED','OFFER','NOT_RELEVANT'}:state='SUPPRESSED'
            elif not ats_for(job['application_url'] or ''):state='UNSUPPORTED_ROUTE' if eligibility=='PASS' else state
            if identity in identities and state=='PENDING':state='DUPLICATE'
            if state=='PENDING':identities.add(identity)
            if prior and prior['attempts']>=3 and state=='PENDING':state='REVIEW_REQUIRED';reason='Three persisted preparation attempts exhausted; human reconciliation required.'
            recruiter=sorted(contacts.get(job['job_key'],[]),key=lambda m:(-m['tier'],m['deadline'] or '9999'))
            tier=recruiter[0]['tier'] if recruiter else 0;deadline=recruiter[0]['deadline'] if recruiter else None
            if tier:reason='Verified recruiter-linked opportunity: '+recruiter[0]['reason']+'. '+reason
            fingerprint=digest([profile,job,hard,assessment,contacts.get(job['job_key'],[])])
            decisions.append((job['id'],identity,state,float(job['match_score']),tier,deadline,job.get('published_at'),sources.get(job['id'],'unknown'),reason,eligibility,fingerprint,prior['queued_at'] if prior else now(),prior['last_processed'] if prior else (app.get('last_sync_at') or app.get('updated_at')) if app else None,now()))
        conn.executemany('''INSERT INTO application_priority(job_id,identity,state,fit,recruiter_tier,deadline,freshness,source,reason,eligibility,evidence_hash,queued_at,last_processed,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(job_id) DO UPDATE SET identity=excluded.identity,state=excluded.state,fit=excluded.fit,recruiter_tier=excluded.recruiter_tier,deadline=excluded.deadline,freshness=excluded.freshness,source=excluded.source,reason=excluded.reason,eligibility=excluded.eligibility,evidence_hash=excluded.evidence_hash,updated_at=excluded.updated_at''',decisions)
    return snapshot(db)


def warm_messages(db):
    """Classify only received messages already cached locally. Never opens Gmail."""
    import hashlib
    from .gmail_local import message_from_api
    with db.transaction() as conn:ids=[r[0] for r in conn.execute('SELECT message_id FROM gmail_intake WHERE message_id NOT IN (SELECT message_id FROM message_priority WHERE version=?)',(VERSION,))]
    for mid in ids:
        path=db.path.parent/'gmail/message-cache'/(hashlib.sha256(mid.encode()).hexdigest()+'.json')
        if not path.is_file() or path.stat().st_size>3*1024*1024:continue
        try:
            message=message_from_api(json.loads(path.read_text(encoding='utf-8')))
            if message and message.message_id==mid:record_message(db,message)
        except (ValueError,KeyError,TypeError):continue


def lead_priorities(db):
    with db.transaction() as conn:
        rows=conn.execute("SELECT r.job_id,p.* FROM source_references r JOIN message_priority p ON p.message_id=r.source_job_id WHERE r.source='gmail' ORDER BY p.tier DESC,COALESCE(p.deadline,'9999'),p.message_id").fetchall()
    result={}
    for row in rows:result.setdefault(row['job_id'],dict(row))
    return result


ORDER="recruiter_tier DESC,fit DESC,COALESCE(deadline,'9999') ASC,COALESCE(freshness,'') DESC,job_id ASC"


def candidates(db,limit=5,job_ids=None):
    with db.transaction() as conn:
        rows=[dict(r) for r in conn.execute('SELECT * FROM application_priority WHERE state=\'PENDING\' AND attempts<3 ORDER BY '+ORDER)]
    if job_ids is not None:rows=[r for r in rows if r['job_id'] in set(job_ids)]
    selected=rows[:limit]
    waiting=sorted((r for r in rows if r['skips']>=3 and r not in selected),key=lambda r:(-r['skips'],r['queued_at'],r['job_id']))
    if waiting and selected:selected[-1]={**waiting[0],'reason':'Fairness slot after three skipped review batches. '+waiting[0]['reason']}
    return selected


def reserve(conn,job_id,batch_id,position,reason):
    changed=conn.execute("UPDATE application_priority SET state='RESERVED',batch_id=?,reserved_order=?,reason=?,attempts=attempts+1,last_processed=?,updated_at=? WHERE job_id=? AND state='PENDING' AND attempts<3",(batch_id,position,reason,now(),now(),job_id)).rowcount
    if changed!=1:raise ValueError('priority_reservation_changed')


def snapshot(db):
    with db.transaction() as conn:
        rows=[dict(r) for r in conn.execute('SELECT q.*,j.title,j.company FROM application_priority q JOIN jobs j ON j.id=q.job_id ORDER BY '+ORDER)]
    position=0
    for row in rows:
        if row['state']=='PENDING':position+=1;row['queue_position']=position
        else:row['queue_position']=None
    return {'version':VERSION,'items':rows,'pending':position,'verification':sum(r['state']=='VERIFICATION' for r in rows)}

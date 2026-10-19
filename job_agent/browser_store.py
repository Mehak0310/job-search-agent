"""Durable browser preparation state over the existing SQLite database."""
import json
import re
import uuid
from urllib.parse import urlsplit,parse_qs
from .database import now
from .runtime_policy import digest

STATES={'PREPARING','NEEDS_LOGIN','NEEDS_USER_ANSWER','NEEDS_EMPLOYER_CHECK',
        'READY_FOR_USER_REVIEW','USER_REPORTED_SUBMITTED','SUBMISSION_CONFIRMED','SESSION_LOST','ERROR'}


def ats_for(url):
    p=urlsplit(url);host=p.hostname or ''
    if host in {'job-boards.greenhouse.io','boards.greenhouse.io','job-boards.eu.greenhouse.io'}:return 'greenhouse'
    if host in {'jobs.lever.co','jobs.eu.lever.co'}:return 'lever'
    if host=='jobs.ashbyhq.com':return 'ashby'
    if parse_qs(p.query).get('gh_jid'):return 'greenhouse'
    return None


def vacancy_identity(job):
    job=dict(job);url=job.get('canonical_application_url') or job.get('application_url') or ''
    p=urlsplit(url);query=parse_qs(p.query)
    match=re.search(r'/jobs/(\d+)',p.path)
    identifier=(query.get('gh_jid') or [match.group(1) if match else None])[0]
    if ats_for(url)=='lever':identifier=p.path.strip('/').split('/')[1] if len(p.path.strip('/').split('/'))>1 else None
    return digest([(job['company'] or '').casefold().strip(),ats_for(url),identifier or [p.hostname,p.path.rstrip('/')]])


class BrowserStore:
    def __init__(self,db):self.db=db

    def job(self,job_id,require_verified=False):
        with self.db.transaction() as conn:
            row=conn.execute('''SELECT j.*,s.job_key,s.readiness,s.lifecycle,s.missing_facts,s.india_state,s.active_state,s.headcount_state,s.payroll_state,p.packet_id,p.current_version
                FROM jobs j JOIN job_operational_state s ON s.job_id=j.id
                JOIN application_packets p ON p.job_key=s.job_key WHERE j.id=?''',(job_id,)).fetchone()
        if not row:raise ValueError('prepared_job_not_found')
        from .application_state import submission_projection,SUBMITTED
        with self.db.transaction() as conn:
            if submission_projection(conn,job_id)['application_outcome'] in SUBMITTED:raise ValueError('existing_submission_history')
        from .employer_evidence import reuse_large_employer_check
        job=reuse_large_employer_check(self.db,dict(row))
        from .requirements import assess_requirements
        with self.db.transaction() as conn:
            profile=json.loads(conn.execute('SELECT config FROM candidate_profiles_v2 ORDER BY version DESC LIMIT 1').fetchone()[0])
            evidence=[dict(e) for e in conn.execute('SELECT * FROM job_evidence WHERE job_key=?',(job['job_key'],))]
        verdict=assess_requirements(profile,job,evidence)
        if verdict['state']=='FAIL':raise ValueError('confirmed_failed_mandatory_requirements')
        # A recruiter recipient is an email prerequisite, not a portal eligibility gate.
        missing=[m for m in json.loads(job['missing_facts'] or '[]') if m!='verified_recipient']
        if verdict['state']!='PASS' and 'mandatory_requirements' not in missing:missing.append('mandatory_requirements')
        if verdict['state']=='PASS':missing=[m for m in missing if m!='mandatory_requirements']
        job['missing_facts']=json.dumps(missing);job['requirement_assessment']=verdict
        if require_verified and (verdict['state']!='PASS' or any(job[g]!='PASS' for g in ('india_state','active_state','headcount_state','payroll_state'))):raise ValueError('unknown_eligibility_requires_verification')
        if job['status']=='SUBMITTED' or job['lifecycle']=='CLOSED' or job['readiness'] in {'EXCLUDED','ACCESS_BLOCKED'} or job['activity_status']=='CLOSED':
            raise ValueError('incompatible_or_already_applied')
        if any(job[key]=='FAIL' for key in ('india_state','active_state','headcount_state','payroll_state')):raise ValueError('confirmed_failed_eligibility_check')
        if job['work_mode']=='remote' and 'india' not in job['location'].casefold() and re.search(r'\b(?:US|United States|Canada|United Kingdom|Europe only)\b',job['location'],re.I):
            raise ValueError('incompatible_known_remote_country_scope')
        if re.search(r'\bcontract\b|third.party payroll',job['title'],re.I):raise ValueError('confirmed_incompatible_employment')
        if not ats_for(job['application_url'] or ''):raise ValueError('unsupported_ats_route')
        identity=vacancy_identity(job)
        with self.db.transaction() as conn:
            profile=json.loads(conn.execute('SELECT config FROM candidate_profiles_v2 ORDER BY version DESC LIMIT 1').fetchone()[0])
            allowed=profile.get('preferred_locations',[])
            if job['work_mode'] in {'hybrid','onsite'} and allowed:
                aliases={'gurgaon':'gurugram','delhi ncr':'noida delhi gurugram greater noida'}
                local=job['location'].casefold().replace('gurgaon','gurugram')
                accepted=[aliases.get(value.casefold(),value.casefold()) for value in allowed if 'remote' not in value.casefold()]
                if accepted and not any(any(part and part in local for part in [value] if value!='noida delhi gurugram greater noida') or (value=='noida delhi gurugram greater noida' and any(v in local for v in ('noida','delhi','gurugram'))) for value in accepted):
                    raise ValueError('incompatible_known_office_location')
            # Cross-source aliases sharing the same proven employer/requisition.
            for other in conn.execute("SELECT company,application_url FROM jobs WHERE status='SUBMITTED'"):
                if other['application_url'] and vacancy_identity(other)==identity:raise ValueError('existing_submission_history')
            prior=conn.execute("SELECT state FROM browser_applications WHERE identity=?",(identity,)).fetchone()
        if prior and prior['state'] in {'USER_REPORTED_SUBMITTED','SUBMISSION_CONFIRMED'}:raise ValueError('existing_submission_history')
        from .review_queue import hidden_job_ids
        if job_id in hidden_job_ids(self.db):raise ValueError('removed_from_active_review')
        return job

    def batch(self,job_ids=None,limit=5,reconstruct=False):
        if not 1<=limit<=5:raise ValueError('review_batch_limit_1_to_5')
        if job_ids and len(job_ids)>5:raise ValueError('review_batch_limit_1_to_5')
        from .priority_queue import refresh,candidates,reserve
        refresh(self.db)
        if reconstruct and job_ids:
            with self.db.transaction() as conn:
                for key in job_ids:conn.execute("UPDATE application_priority SET state='REVIEW_REQUIRED' WHERE job_id=? AND state='RESERVED' AND NOT EXISTS(SELECT 1 FROM browser_workflows w WHERE w.batch_id=application_priority.batch_id AND w.state IN ('QUEUED','RUNNING')) AND EXISTS(SELECT 1 FROM browser_applications a WHERE a.job_id=application_priority.job_id AND a.state='SESSION_LOST')",(key,))
                for key in job_ids:conn.execute("UPDATE application_priority SET state='PENDING' WHERE job_id=? AND eligibility='PASS' AND attempts<3 AND state IN ('EXISTING_PROGRESS','REVIEW_REQUIRED') AND EXISTS(SELECT 1 FROM browser_applications a WHERE a.job_id=application_priority.job_id AND a.state='SESSION_LOST')",(key,))
        requested=job_ids
        ranked=candidates(self.db,limit,job_ids)
        job_ids=[r['job_id'] for r in ranked]
        selected=[];skipped=[]
        if requested:skipped=[{'job_id':i,'reason':'not_in_verified_pending_priority_queue'} for i in requested if i not in job_ids]
        for job_id in job_ids:
            try:
                from .m3 import M3Engine
                with self.db.transaction() as conn:packet=conn.execute('SELECT 1 FROM application_packets WHERE job_id=?',(job_id,)).fetchone()
                if not packet:
                    with self.db.transaction() as conn:key=conn.execute('SELECT job_key FROM job_operational_state WHERE job_id=?',(job_id,)).fetchone()[0]
                    M3Engine(self.db).prepare(key)
                job=self.job(job_id,require_verified=True)
            except ValueError as error:skipped.append({'job_id':job_id,'reason':str(error)});continue
            with self.db.transaction() as conn:prior=conn.execute('SELECT id,state FROM browser_applications WHERE identity=?',(vacancy_identity(job),)).fetchone()
            if prior and not reconstruct:
                skipped.append({'job_id':job_id,'reason':'existing_preparation','application_id':prior['id']});continue
            selected.append(job)
            if len(selected)==limit:break
        identifier=uuid.uuid4().hex
        with self.db.transaction() as conn:
            conn.execute('BEGIN IMMEDIATE')
            if selected and conn.execute("SELECT 1 FROM browser_batches b JOIN browser_applications a ON a.batch_id=b.id WHERE b.status IN ('QUEUED','RUNNING') AND a.application_outcome='NOT_SUBMITTED' AND a.preparation_state='PREPARING' AND a.session_health<>'LOST' LIMIT 1").fetchone():raise ValueError('active_batch_already_exists')
            conn.execute("INSERT INTO browser_batches(id,status,created_at,finished_at,error_code) VALUES(?,'QUEUED',?,NULL,NULL)",(identifier,now()))
            for job in selected:
                reserve(conn,job['id'],identifier,job_ids.index(job['id'])+1,next(r['reason'] for r in ranked if r['job_id']==job['id']))
                identity=vacancy_identity(job);prior=conn.execute('SELECT * FROM browser_applications WHERE identity=?',(identity,)).fetchone()
                if prior:
                    if prior['state']!='SESSION_LOST':raise ValueError('reconstruction_requires_session_lost_and_progress_review')
                    conn.execute("UPDATE browser_applications SET batch_id=?,state='PREPARING',preparation_state='PREPARING',session_health='UNKNOWN',phase='Awaiting preparation',target_id=NULL,session_id=NULL,updated_at=? WHERE id=?",(identifier,now(),prior['id']))
                else:
                    conn.execute('''INSERT INTO browser_applications(id,batch_id,job_id,identity,url,ats,state,updated_at)
                      VALUES(?,?,?,?,?,?,'PREPARING',?)''',(uuid.uuid4().hex,identifier,job['id'],identity,job['application_url'],ats_for(job['application_url']),now()))
            if not selected:conn.execute("UPDATE browser_batches SET status='EMPTY',finished_at=? WHERE id=?",(now(),identifier))
            if selected:conn.execute("UPDATE application_priority SET skips=skips+1 WHERE state='PENDING'")
            self.db.audit(conn,'BROWSER_BATCH_CREATED',{'batch_id':identifier,'count':len(selected)})
        return {'batch_id':identifier,'selected':len(selected),'skipped':skipped,'applications':self.list(identifier)}

    def list(self,batch_id=None,include_history=False):
        with self.db.transaction() as conn:
            rows=conn.execute('''SELECT a.*,j.company,j.title FROM browser_applications a JOIN jobs j ON j.id=a.job_id
              WHERE (? IS NULL OR a.batch_id=?) ORDER BY a.updated_at DESC''',(batch_id,batch_id)).fetchall()
        from .review_queue import hidden_job_ids
        hidden=set() if include_history else hidden_job_ids(self.db)
        out=[]
        for row in rows:
            if row["job_id"] in hidden:continue
            value=dict(row)
            for key in ('inspection','missing','checks','documents'):value[key]=json.loads(value[key])
            from .application_state import submission_projection,status_message
            with self.db.transaction() as conn:value.update(submission_projection(conn,value['job_id']))
            value['status_message']=status_message(value)
            with self.db.transaction() as conn:
                state=conn.execute('SELECT headcount_state,payroll_state,india_state,active_state FROM job_operational_state WHERE job_id=? LIMIT 1',(value['job_id'],)).fetchone()
            if state:
                resolved={name for name,column in [('headcount','headcount_state'),('direct_permanent_payroll','payroll_state'),('india_eligible','india_state'),('active','active_state')] if state[column]=='PASS'}
                value['checks']=[c for c in value['checks'] if c not in resolved]
            # Dashboard gets metadata/questions, not copied private input values.
            value['answer_resolutions']=[{k:f.get(k) for k in ('label','state','explanation')} for f in value['inspection'].get('answer_resolution',{}).get('fields',[])]
            value['inspection']={key:value['inspection'].get(key) for key in ('verified_at','field_count','ats','jd_sha256','error_code','upload_note','stage','answered')}
            out.append(value)
        return out

    def get(self,application_id):
        with self.db.transaction() as conn:row=conn.execute('SELECT * FROM browser_applications WHERE id=?',(application_id,)).fetchone()
        if not row:raise ValueError('browser_application_not_found')
        return dict(row)

    def update(self,application_id,**values):
        allowed={'state','target_id','session_id','inspection','missing','checks','documents','confirmation_ref','session_health','last_sync_at','phase','completed_fields','retry_condition'}
        if set(values)-allowed:raise ValueError('invalid_browser_state_field')
        if 'state' in values and values['state'] not in STATES:raise ValueError('invalid_browser_state')
        with self.db.transaction() as conn:
            conn.execute('BEGIN IMMEDIATE')
            current=conn.execute('SELECT * FROM browser_applications WHERE id=?',(application_id,)).fetchone()
            if not current:raise ValueError('browser_application_not_found')
            from .application_state import SUBMITTED,valid_confirmation
            previous=current['application_outcome'];requested=values.get('state')
            outcome=previous
            if requested=='SUBMISSION_CONFIRMED':
                if not valid_confirmation(values.get('confirmation_ref') or current['confirmation_ref']):raise ValueError('confirmation_evidence_required')
                if previous!='SUBMISSION_CONFIRMED':
                    from .document_manifest import sha256
                    evidence=self.db.path.parent/'browser-applications'/(application_id+'-confirmation.png')
                    if not evidence.is_file() or sha256(evidence)!=(values.get('confirmation_ref') or current['confirmation_ref']).split(':',1)[1]:raise ValueError('confirmation_evidence_required')
                outcome=requested
            elif requested=='USER_REPORTED_SUBMITTED' and previous!='SUBMISSION_CONFIRMED':outcome=requested
            values['application_outcome']=outcome
            if requested=='SESSION_LOST':values['session_health']='LOST'
            elif requested and requested not in SUBMITTED:values['preparation_state']=requested
            if requested and requested!='PREPARING':values.setdefault('phase','Human review or agent checks required' if requested not in SUBMITTED else 'Application outcome recorded')
            if values.get('target_id'):values['session_health']='CONNECTED'
            if requested or 'session_health' in values:values['state']=outcome if outcome in SUBMITTED else ('SESSION_LOST' if values.get('session_health',current['session_health'])=='LOST' else values.get('preparation_state',current['preparation_state']))
            if 'inspection' in values:
                incoming=values['inspection'];inspection=json.loads(current['inspection']);inspection.update(incoming);values['inspection']=inspection
                if incoming.get('stage'):values['phase']=incoming['stage']
                if inspection.get('answered') is not None:values['completed_fields']=inspection['answered']
            data={key:json.dumps(value,sort_keys=True) if key in {'inspection','missing','checks','documents'} else value for key,value in values.items()}
            data['updated_at']=now()
            conn.execute('UPDATE browser_applications SET '+','.join(key+'=?' for key in data)+' WHERE id=?',(*data.values(),application_id))
            conn.execute('INSERT INTO browser_events(application_id,event,details,created_at) VALUES(?,?,?,?)',
                (application_id,'STATE_CHECKPOINT',json.dumps({'state':values.get('state'),'application_outcome':outcome,'session_health':values.get('session_health',current['session_health']),'field_count':values.get('inspection',{}).get('field_count')}),now()))

        from .orchestration import record_progress
        record_progress(self.db,application_id)

    def begin_operation(self,application_id,kind,payload,write=False):
        if getattr(self,'worker_guard',None):self.worker_guard()
        identifier=digest([application_id,kind,payload])
        with self.db.transaction() as conn:
            conn.execute('BEGIN IMMEDIATE')
            from .application_state import submission_projection,SUBMITTED
            application=conn.execute('SELECT job_id FROM browser_applications WHERE id=?',(application_id,)).fetchone()
            if application and submission_projection(conn,application['job_id'])['application_outcome'] in SUBMITTED:raise ValueError('existing_submission_history')
            row=conn.execute('SELECT * FROM browser_operations WHERE id=?',(identifier,)).fetchone()
            if row and row['state']=='SUCCEEDED':return identifier,False
            if row and (row['state']=='UNCERTAIN' or (write and row['state']=='PENDING')):raise ValueError('uncertain_write_requires_reconciliation')
            if row and row['attempts']>=3:raise ValueError('retry_budget_exhausted')
            if row and row['state']=='BLOCKED':raise ValueError('operation_blocked_requires_fix')
            conn.execute('''INSERT INTO browser_operations VALUES(?,?,?,1,'PENDING',NULL,?,NULL)
              ON CONFLICT(id) DO UPDATE SET attempts=attempts+1,state='PENDING',updated_at=excluded.updated_at''',(identifier,application_id,kind,now()))
        return identifier,True

    def end_operation(self,identifier,state,error=None):
        with self.db.transaction() as conn:conn.execute('UPDATE browser_operations SET state=?,error_code=?,updated_at=?,next_action=? WHERE id=?',
            (state,error,now(),'Review evidence before explicit retry' if state in {'UNCERTAIN','BLOCKED'} else None,identifier))

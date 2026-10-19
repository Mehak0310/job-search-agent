"""Shared outcome projection. Browser health cannot undo a submission event."""
import re

SUBMITTED={'USER_REPORTED_SUBMITTED','SUBMISSION_CONFIRMED'}
LABELS={'NOT_SUBMITTED':'Not submitted','USER_REPORTED_SUBMITTED':'Marked submitted manually; not independently verified',
        'SUBMISSION_CONFIRMED':'Submission confirmed by recorded employer evidence'}


def valid_confirmation(reference):
    return bool(re.fullmatch(r'browser-confirmation:[0-9a-f]{64}',reference or ''))


def submission_projection(conn,job_id):
    from .browser_store import vacancy_identity
    job=conn.execute('SELECT id,company,application_url,canonical_application_url,status FROM jobs WHERE id=?',(job_id,)).fetchone()
    if not job:return {'application_outcome':'NOT_SUBMITTED','submission_label':LABELS['NOT_SUBMITTED'],'submission_verified':False}
    identity=vacancy_identity(job)
    aliases=list({job_id}|{r['id'] for r in conn.execute('SELECT id,company,application_url,canonical_application_url FROM jobs WHERE lower(trim(company))=lower(trim(?))',(job['company'],)) if vacancy_identity(r)==identity})
    outcome='NOT_SUBMITTED';reference=None
    for identifier in aliases:
        for row in conn.execute('SELECT id,application_outcome,confirmation_ref,state FROM browser_applications WHERE job_id=?',(identifier,)):
            if row['application_outcome']=='SUBMISSION_CONFIRMED' and valid_confirmation(row['confirmation_ref']):
                outcome='SUBMISSION_CONFIRMED';reference=row['confirmation_ref'];break
            if row['application_outcome'] in SUBMITTED or row['state'] in SUBMITTED:outcome='USER_REPORTED_SUBMITTED'
            if conn.execute("SELECT 1 FROM browser_events WHERE application_id=? AND json_extract(details,'$.state') IN ('USER_REPORTED_SUBMITTED','SUBMISSION_CONFIRMED') LIMIT 1",(row['id'],)).fetchone():outcome='USER_REPORTED_SUBMITTED'
        if outcome=='SUBMISSION_CONFIRMED':break
        if conn.execute("SELECT 1 FROM status_history WHERE job_id=? AND status='SUBMITTED' LIMIT 1",(identifier,)).fetchone() or conn.execute("SELECT 1 FROM jobs WHERE id=? AND status='SUBMITTED'",(identifier,)).fetchone():outcome='USER_REPORTED_SUBMITTED'
    return {'application_outcome':outcome,'submission_label':LABELS[outcome],'submission_verified':outcome=='SUBMISSION_CONFIRMED','confirmation_ref':reference}


def status_message(row):
    if row['application_outcome'] in SUBMITTED:return LABELS[row['application_outcome']]
    if row['session_health']=='LOST':return 'Browser session lost; application history preserved'
    return {'PREPARING':'Preparing your application','NEEDS_LOGIN':'Waiting for browser login',
            'NEEDS_USER_ANSWER':'A required answer or manual declaration remains',
            'NEEDS_EMPLOYER_CHECK':'Employer verification pending','READY_FOR_USER_REVIEW':'Ready for your review; not submitted',
            'ERROR':'Preparation blocked; check the recorded error and retry condition',
            'AWAITING_INSPECTION':'Existing progress needs inspection'}.get(row['preparation_state'],'Agent inspection required')

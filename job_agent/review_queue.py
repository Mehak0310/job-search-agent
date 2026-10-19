"""Durable review suppression without deleting jobs or inventing submissions."""
from urllib.parse import urlsplit
from .browser_store import vacancy_identity


def usable_url(value):
    try:
        p=urlsplit(value or '')
        return p.scheme in {'https','http'} and bool(p.hostname) and not p.username and not p.password
    except ValueError:return False


def hidden_job_ids(db):
    with db.transaction() as conn:
        jobs=[dict(r) for r in conn.execute('SELECT id,company,application_url,canonical_application_url,status,activity_status FROM jobs')]
        submitted={r[0] for r in conn.execute("SELECT job_id FROM browser_applications WHERE application_outcome IN ('USER_REPORTED_SUBMITTED','SUBMISSION_CONFIRMED') OR state IN ('USER_REPORTED_SUBMITTED','SUBMISSION_CONFIRMED')")}
        submitted.update(r[0] for r in conn.execute("SELECT DISTINCT a.job_id FROM browser_events e JOIN browser_applications a ON a.id=e.application_id WHERE json_extract(e.details,'$.state') IN ('USER_REPORTED_SUBMITTED','SUBMISSION_CONFIRMED')"))
        submitted.update(r[0] for r in conn.execute("SELECT DISTINCT job_id FROM status_history WHERE status='SUBMITTED'"))
        dismissed={r[0] for r in conn.execute("SELECT job_key FROM job_evidence WHERE kind='review_queue_dismissal' AND state='USER_REPORTED_UNAVAILABLE'")}
        states=[dict(r) for r in conn.execute('SELECT job_id,job_key,lifecycle,active_state FROM job_operational_state')]
        keys={r['job_id']:r['job_key'] for r in states}
        unavailable={r['job_id'] for r in states if r['lifecycle']=='CLOSED' or r['active_state']=='FAIL'}
    processed={'SUBMITTED','INTERVIEW','REJECTED','OFFER','NOT_RELEVANT'}
    identities={j['id']:vacancy_identity(j) for j in jobs}
    suppressed_identities={identities[j['id']] for j in jobs
        if j['status'] in processed or j['id'] in submitted
        or keys.get(j['id'],'job:'+j['id']) in dismissed}
    return {j['id'] for j in jobs
        if j['status'] in processed or j['id'] in submitted
        or j['id'] in unavailable or j['activity_status']=='CLOSED'
        or not usable_url(j['canonical_application_url'] or j['application_url'])
        or identities[j['id']] in suppressed_identities}

"""Auxiliary durable state over R1 journals. No daemon, schedule activation or sends."""
import json
import re
import uuid
from datetime import datetime,timedelta,timezone
from .database import now
from .runtime_policy import digest

STAGES={'DISCOVERY','GMAIL_INTAKE','VERIFICATION','PREPARATION','NOTIFICATIONS'}
IST=timezone(timedelta(hours=5,minutes=30))


def schema(conn):
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS local_notifications(
      id TEXT PRIMARY KEY,operation_key TEXT NOT NULL UNIQUE,batch_id TEXT,kind TEXT NOT NULL,
      payload TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 1,ack_revision INTEGER NOT NULL DEFAULT 0,
      snooze_until TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS notification_preferences(id INTEGER PRIMARY KEY CHECK(id=1),
      sound INTEGER NOT NULL DEFAULT 0,desktop INTEGER NOT NULL DEFAULT 0,quiet_start INTEGER NOT NULL DEFAULT 22,quiet_end INTEGER NOT NULL DEFAULT 8);
    INSERT OR IGNORE INTO notification_preferences(id) VALUES(1);
    CREATE TABLE IF NOT EXISTS local_schedule_plans(id TEXT PRIMARY KEY,stage TEXT NOT NULL,
      interval_seconds INTEGER NOT NULL,next_run TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 0,
      last_attempt TEXT,last_success TEXT,error TEXT,lease_until TEXT,operation_key TEXT);
    CREATE TABLE IF NOT EXISTS local_schedule_runs(operation_key TEXT PRIMARY KEY,schedule_id TEXT NOT NULL,
      due_at TEXT NOT NULL,state TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,updated_at TEXT NOT NULL,error TEXT);
    CREATE TABLE IF NOT EXISTS application_plans(id TEXT PRIMARY KEY,job_ids TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'PLANNED',created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS employer_login_waits(application_id TEXT PRIMARY KEY,batch_id TEXT NOT NULL,
      started_at TEXT NOT NULL,deadline TEXT NOT NULL,state TEXT NOT NULL,verified_at TEXT,error TEXT);
    CREATE TABLE IF NOT EXISTS answer_resume_queue(id TEXT PRIMARY KEY,application_ids TEXT NOT NULL,
      state TEXT NOT NULL DEFAULT 'PENDING',created_at TEXT NOT NULL);
    ''')


def publish(db,key,batch_id,kind,payload):
    value=json.dumps(payload,sort_keys=True)
    with db.transaction() as c:
        c.execute('''INSERT INTO local_notifications(id,operation_key,batch_id,kind,payload,created_at,updated_at)
          VALUES(?,?,?,?,?,?,?) ON CONFLICT(operation_key) DO UPDATE SET payload=excluded.payload,
          revision=local_notifications.revision+1,updated_at=excluded.updated_at WHERE local_notifications.payload!=excluded.payload''',
          (uuid.uuid4().hex,key,batch_id,kind,value,now(),now()))


def notifications(db,at=None):
    stamp=datetime.fromisoformat(at or now());local=stamp.astimezone(IST)
    with db.transaction() as c:
        preferences=dict(c.execute('SELECT * FROM notification_preferences WHERE id=1').fetchone())
        rows=[dict(r) for r in c.execute('SELECT * FROM local_notifications ORDER BY updated_at DESC,id')]
    start,end=preferences['quiet_start'],preferences['quiet_end'];hour=local.hour
    quiet=(hour>=start or hour<end) if start>end else start<=hour<end
    for row in rows:
        row['payload']=json.loads(row['payload']);row['unread']=row['revision']>row['ack_revision']
        row['resolved']=bool(row['payload'].get('resolved'))
        row['attention']=not row['resolved'] and row['unread'] and (not row['snooze_until'] or datetime.fromisoformat(row['snooze_until'])<=stamp)
        row['audible']=row['attention'] and not quiet and bool(preferences['sound'])
    return {'items':rows,'preferences':preferences,'quiet':quiet,'timezone':'Asia/Calcutta','os_delivery':'browser_permission_and_open_page_required'}


def resolve_notification(db,key):
    """Retain a condition's record without advertising obsolete work or sounding."""
    with db.transaction() as c:
        row=c.execute('SELECT id,payload FROM local_notifications WHERE operation_key=?',(key,)).fetchone()
        if not row:return
        payload=json.loads(row['payload'])
        if payload.get('resolved'):return
        payload.update(resolved=True,message='Resolved; this batch condition no longer requires action.')
        c.execute('UPDATE local_notifications SET payload=?,revision=revision+1,ack_revision=revision+1,snooze_until=NULL,updated_at=? WHERE id=?',
                  (json.dumps(payload,sort_keys=True),now(),row['id']))


def acknowledge(db,identifier,revision,snooze_minutes=0):
    if not 0<=snooze_minutes<=1440:raise ValueError('invalid_snooze')
    with db.transaction() as c:
        row=c.execute('SELECT revision FROM local_notifications WHERE id=?',(identifier,)).fetchone()
        if not row or row['revision']!=revision:raise ValueError('notification_changed')
        until=(datetime.now(timezone.utc)+timedelta(minutes=snooze_minutes)).isoformat() if snooze_minutes else None
        c.execute('UPDATE local_notifications SET ack_revision=CASE WHEN ?=0 THEN revision ELSE ack_revision END,snooze_until=? WHERE id=?',(snooze_minutes,until,identifier))


def batch_questions(db,batch_id):
    from .browser_store import BrowserStore
    from .review_workflow import pending_questions
    groups={}
    for app in BrowserStore(db).list(batch_id):
        for q in pending_questions(db,app['id']):
            sensitive=bool(re.search(r'previous|ever worked|consult|restrict|conflict|sponsor|authoriz|why|motivat|company',q['label'],re.I))
            scope=q['company'].casefold().strip() if sensitive else 'explicit_batch_answer'
            key=digest([q['label'].casefold().strip(),scope,q['options'],q['max_length']])
            item=groups.setdefault(key,{'id':key,'label':q['label'],'options':q['options'],'max_length':q['max_length'],'scope':scope,'targets':[]})
            item['targets'].append({'application_id':app['id'],'key':q['key'],'company':q['company']})
    return list(groups.values())


def save_batch_answers(db,batch_id,answers):
    from .application_answers import question_key
    from .service import JobService
    from .reconciliation_r2 import reconcile
    questions={q['id']:q for q in batch_questions(db,batch_id)};values={};scopes={};affected=set()
    if not answers:raise ValueError('answers_required')
    seen=set()
    for item in answers:
        q=questions.get(item['id']);value=str(item['value']).strip()
        if not q or not value or item['id'] in seen:raise ValueError('question_changed_or_answer_empty')
        seen.add(item['id'])
        if q['options'] and value not in q['options']:raise ValueError('answer_not_in_options')
        if q['max_length']>0 and len(value)>q['max_length']:raise ValueError('answer_exceeds_character_limit')
        for target in q['targets']:
            key=question_key(q['label'],target['company']);values[key]=value
            scopes[key]='employer:'+target['company'].casefold().strip();affected.add(target['application_id'])
    result=JobService(db).record_confirmed_application_answers(values,'Explicit consolidated batch answer confirmation',scopes)
    result['reconciliation']=reconcile(db);result['affected_applications']=sorted(affected)
    return result


def record_progress(db,identifier):
    with db.transaction() as c:
        row=c.execute('SELECT batch_id,state,inspection,missing FROM browser_applications WHERE id=?',(identifier,)).fetchone()
        if not row:return
        batch_id=row['batch_id'];counts={r['state']:r['n'] for r in c.execute('SELECT state,COUNT(*) n FROM browser_applications WHERE batch_id=? GROUP BY state',(batch_id,))}
        ready_ids=sorted(r[0] for r in c.execute("SELECT id FROM browser_applications WHERE batch_id=? AND state='READY_FOR_USER_REVIEW'",(batch_id,)))
    if row['state']=='NEEDS_LOGIN':
        publish(db,batch_id+':login',batch_id,'LOGIN_REQUIRED',{'message':'Complete login or human verification in the dedicated browser. Credentials and MFA stay there.'})
        code=json.loads(row['inspection']).get('error_code','')
        if code in {'authentication_required','login_required'}:
            with db.transaction() as c:c.execute("INSERT OR IGNORE INTO employer_login_waits VALUES(?,?,?,?, 'WAITING',NULL,NULL)",(identifier,batch_id,now(),(datetime.now(timezone.utc)+timedelta(seconds=240)).isoformat()))
    if not counts.get('NEEDS_LOGIN'):resolve_notification(db,batch_id+':login')
    if ready_ids:publish(db,batch_id+':ready',batch_id,'READY',{'ready':len(ready_ids),'application_ids':ready_ids,'message':'Forms are ready for your personal review and submission.'})
    else:resolve_notification(db,batch_id+':ready')
    if counts.get('NEEDS_USER_ANSWER') and not counts.get('PREPARING'):
        questions=batch_questions(db,batch_id)
        if questions:publish(db,batch_id+':questions',batch_id,'MISSING_INFORMATION',{'count':len(questions),'question_ids':sorted(q['id'] for q in questions),'message':'Review consolidated missing questions; approved facts were checked first.'})
        else:resolve_notification(db,batch_id+':questions')
    elif not counts.get('NEEDS_USER_ANSWER'):resolve_notification(db,batch_id+':questions')


def login_tick(db,identifier,*,authenticated=False,at=None):
    stamp=at or now()
    with db.transaction() as c:
        row=c.execute('SELECT * FROM employer_login_waits WHERE application_id=?',(identifier,)).fetchone()
        app=c.execute('SELECT application_outcome,session_health FROM browser_applications WHERE id=?',(identifier,)).fetchone()
        if not row:return 'HUMAN_ONLY'
        if row['state']!='WAITING':return row['state']
        state='CANCELLED' if app['application_outcome']!='NOT_SUBMITTED' or app['session_health']=='LOST' else 'TIMEOUT' if stamp>=row['deadline'] else 'VERIFIED' if authenticated else 'WAITING'
        c.execute('UPDATE employer_login_waits SET state=?,verified_at=? WHERE application_id=?',(state,stamp if state=='VERIFIED' else None,identifier))
        return state


def plan_batches(db):
    from .priority_queue import refresh,candidates
    refresh(db)
    with db.transaction() as c:
        c.execute('BEGIN IMMEDIATE')
        existing=[dict(r) for r in c.execute("SELECT * FROM application_plans WHERE state='PLANNED' ORDER BY created_at,id")]
        used={job for r in existing for job in json.loads(r['job_ids'])}
        ranked=[r['job_id'] for r in candidates(db,20) if r['job_id'] not in used]
        for index in range(3-len(existing)):
            ids=ranked[index*5:(index+1)*5]
            if not ids:break
            c.execute('INSERT INTO application_plans VALUES(?,?,\'PLANNED\',?)',(uuid.uuid4().hex,json.dumps(ids),now()))
    return plans(db)


def plans(db):
    with db.transaction() as c:rows=[dict(r) for r in c.execute('SELECT * FROM application_plans ORDER BY created_at,id')]
    for row in rows:row['job_ids']=json.loads(row['job_ids'])
    return {'items':rows,'max_preplanned':3,'max_active_batches':1,'max_browser_workers':2,'activation':'explicit_prepare_only'}


def schedule_plan(db,stage,interval_seconds,next_run):
    from .policy_hooks import check
    check('scheduler',stage)
    if not 60<=interval_seconds<=604800:raise ValueError('invalid_schedule_interval')
    if datetime.fromisoformat(next_run).tzinfo is None:raise ValueError('timezone_required')
    next_run=datetime.fromisoformat(next_run).astimezone(timezone.utc).isoformat();identifier=uuid.uuid4().hex
    with db.transaction() as c:c.execute('INSERT INTO local_schedule_plans(id,stage,interval_seconds,next_run) VALUES(?,?,?,?)',(identifier,stage,interval_seconds,next_run))
    return identifier


def schedules(db):
    with db.transaction() as c:return {'items':[dict(r) for r in c.execute('SELECT * FROM local_schedule_plans ORDER BY next_run,id')],'activation_enabled':False,'chatgpt_automations':'unchanged; parity not verified'}


def schedule_tick(db,at=None):
    """Pure scheduling decision: persists at most one due item, NEVER executes it.

    Disabled plans cannot be activated through HTTP. A later reviewed release
    must supply approved task adapters and explicit activation authorization.
    """
    stamp=at or now();selected=[]
    with db.transaction() as c:
        for row in c.execute('SELECT * FROM local_schedule_plans WHERE enabled=1 AND next_run<=? ORDER BY next_run,id',(stamp,)).fetchall():
            key=digest([row['id'],row['next_run']])
            c.execute("INSERT OR IGNORE INTO local_schedule_runs VALUES(?,?,?,'AWAITING_APPROVAL',0,?,NULL)",(key,row['id'],row['next_run'],stamp))
            selected.append(key)
    return selected


def run_scheduled(db,adapters,*,approval_reference=None,at=None):
    """Dormant executor. No HTTP activation route, no automatic daemon startup."""
    if not approval_reference:raise ValueError('schedule_activation_requires_separate_approval')
    from .policy_hooks import check
    stamp=at or now();results=[]
    for key in schedule_tick(db,stamp):
        with db.transaction() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT r.*,p.stage,p.interval_seconds FROM local_schedule_runs r JOIN local_schedule_plans p ON p.id=r.schedule_id WHERE r.operation_key=?',(key,)).fetchone()
            if row['state'] not in {'AWAITING_APPROVAL','RETRY'} or row['attempts']>=3:continue
            check('scheduler',row['stage'])
            if row['stage'] not in adapters:continue
            c.execute("UPDATE local_schedule_runs SET state='RUNNING',attempts=attempts+1,updated_at=? WHERE operation_key=?",(stamp,key))
            c.execute('UPDATE local_schedule_plans SET last_attempt=?,lease_until=?,operation_key=? WHERE id=?',(stamp,(datetime.fromisoformat(stamp)+timedelta(seconds=120)).isoformat(),key,row['schedule_id']))
        state='COMPLETED';error=None
        try:adapters[row['stage']](key)
        except (TimeoutError,ConnectionError):
            state='UNCERTAIN' if row['stage']=='PREPARATION' else 'RETRY' if row['attempts']<2 else 'FAILED'
            error='preparation_requires_reconciliation' if state=='UNCERTAIN' else 'transient_failure'
        except Exception:state='BLOCKED';error='adapter_requires_review'
        with db.transaction() as c:
            c.execute('UPDATE local_schedule_runs SET state=?,error=?,updated_at=? WHERE operation_key=?',(state,error,stamp,key))
            c.execute('UPDATE local_schedule_plans SET lease_until=NULL,error=?,last_success=CASE WHEN ?=\'COMPLETED\' THEN ? ELSE last_success END,next_run=CASE WHEN ?=\'COMPLETED\' THEN ? ELSE next_run END WHERE id=?',(error,state,stamp,state,(datetime.fromisoformat(stamp)+timedelta(seconds=row['interval_seconds'])).isoformat(),row['schedule_id']))
        results.append({'operation_key':key,'state':state})
    return results


def recover_schedules(db,at=None):
    stamp=at or now()
    with db.transaction() as c:
        rows=c.execute("SELECT id,operation_key,stage FROM local_schedule_plans WHERE lease_until<?",(stamp,)).fetchall()
        for row in rows:
            state='UNCERTAIN' if row['stage']=='PREPARATION' else 'RETRY'
            c.execute("UPDATE local_schedule_runs SET state=?,error='lease_expired',updated_at=? WHERE operation_key=? AND state='RUNNING'",(state,stamp,row['operation_key']))
            c.execute("UPDATE local_schedule_plans SET lease_until=NULL,error='lease_expired' WHERE id=?",(row['id'],))
    return len(rows)


def queue_resume(db,ids):
    if not ids or len(set(ids))>5:raise ValueError('invalid_resume_scope')
    with db.transaction() as c:c.execute('INSERT INTO answer_resume_queue(id,application_ids,created_at) VALUES(?,?,?)',(uuid.uuid4().hex,json.dumps(sorted(set(ids))),now()))


def dispatch_pending_resumes(db):
    from .browser_applications import launch_sync_worker
    with db.transaction() as c:
        if c.execute("SELECT 1 FROM browser_workflows WHERE state IN ('QUEUED','RUNNING')").fetchone():return None
        rows=[dict(r) for r in c.execute("SELECT * FROM answer_resume_queue WHERE state='PENDING' ORDER BY created_at,id")]
    if not rows:return None
    ids=sorted({identifier for row in rows for identifier in json.loads(row['application_ids'])})[:5]
    try:pid=launch_sync_worker(db,application_ids=ids)
    except ValueError:return None
    with db.transaction() as c:
        for row in rows:
            remaining=[i for i in json.loads(row['application_ids']) if i not in ids]
            c.execute('UPDATE answer_resume_queue SET application_ids=?,state=? WHERE id=?',(json.dumps(remaining),'PENDING' if remaining else 'DISPATCHED',row['id']))
    return pid

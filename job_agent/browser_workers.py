"""Leased operations over existing SQLite journals; recovery never repeats a write."""
import json
import os
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
from .database import now
from .browser_store import BrowserStore

ACTIVE={'QUEUED','RUNNING'}


class BrowserWorkers:
    def __init__(self,db,lease_seconds=30):self.db=db;self.lease_seconds=lease_seconds

    def event(self,conn,identifier,event,details):
        conn.execute('INSERT INTO browser_worker_events(workflow_id,event,details,created_at) VALUES(?,?,?,?)',(identifier,event,json.dumps(details),now()))

    def enqueue(self,kind,ids,batch_id=None):
        from .policy_hooks import check
        check('worker',kind)
        self.recover_expired()
        identifier=uuid.uuid4().hex;stamp=now()
        with self.db.transaction() as conn:
            conn.execute('BEGIN IMMEDIATE')
            prior=conn.execute("SELECT id FROM browser_workflows WHERE state IN ('QUEUED','RUNNING') LIMIT 1").fetchone()
            if prior:raise ValueError('workflow_already_running')
            expiry=(datetime.now(timezone.utc)+timedelta(seconds=self.lease_seconds)).isoformat()
            conn.execute("INSERT INTO browser_workflows(id,kind,batch_id,application_ids,state,phase,created_at,updated_at,lease_until) VALUES(?,?,?,?,'QUEUED','Awaiting worker',?,?,?)",(identifier,kind,batch_id,json.dumps(ids),stamp,stamp,expiry))
            self.event(conn,identifier,'QUEUED',{'kind':kind,'application_count':len(ids)})
        return identifier

    def get(self,identifier):
        with self.db.transaction() as conn:row=conn.execute('SELECT * FROM browser_workflows WHERE id=?',(identifier,)).fetchone()
        if not row:raise ValueError('worker_operation_not_found')
        item=dict(row);item['application_ids']=json.loads(item['application_ids']);return item

    def attach_pid(self,identifier,pid):
        with self.db.transaction() as conn:conn.execute("UPDATE browser_workflows SET worker_pid=? WHERE id=? AND state IN ('QUEUED','RUNNING')",(pid,identifier))

    def claim(self,identifier):
        from .policy_hooks import check
        check('worker',self.get(identifier)['kind'])
        owner=str(os.getpid())+':'+uuid.uuid4().hex
        with self.db.transaction() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row=conn.execute("SELECT state,lease_until FROM browser_workflows WHERE id=?",(identifier,)).fetchone()
            if not row or row['state']!='QUEUED' or row['lease_until']<=now():raise ValueError('worker_lease_unavailable')
            conn.execute("UPDATE browser_workflows SET state='RUNNING',owner=?,worker_pid=?,heartbeat_at=?,lease_until=?,phase='Inspecting application progress',updated_at=? WHERE id=?",(owner,os.getpid(),now(),self.expiry(),now(),identifier))
            self.event(conn,identifier,'CLAIMED',{'owner':owner})
        return owner

    def expiry(self):return (datetime.now(timezone.utc)+timedelta(seconds=self.lease_seconds)).isoformat()

    def assert_owner(self,identifier,owner):
        row=self.get(identifier)
        if row['state']!='RUNNING' or row['owner']!=owner or row['lease_until']<=now():raise ValueError('worker_ownership_lost')

    def heartbeat(self,identifier,owner):
        with self.db.transaction() as conn:
            return conn.execute("UPDATE browser_workflows SET heartbeat_at=?,lease_until=?,updated_at=? WHERE id=? AND owner=? AND state='RUNNING' AND lease_until>?",(now(),self.expiry(),now(),identifier,owner,now())).rowcount==1

    def checkpoint(self,identifier,owner,cursor,phase):
        self.assert_owner(identifier,owner)
        with self.db.transaction() as conn:
            conn.execute("UPDATE browser_workflows SET cursor=?,phase=?,updated_at=? WHERE id=? AND owner=? AND state='RUNNING'",(cursor,phase,now(),identifier,owner))
            self.event(conn,identifier,'CHECKPOINT',{'cursor':cursor,'phase':phase})

    def finish(self,identifier,state='COMPLETED',error=None,owner=None):
        if state not in {'COMPLETED','ERROR','INTERRUPTED'}:raise ValueError('invalid_worker_terminal_state')
        retry='Inspect existing employer progress; uncertain uploads must be reconciled, never replayed.' if state!='COMPLETED' else None
        with self.db.transaction() as conn:
            count=conn.execute("UPDATE browser_workflows SET state=?,phase=?,error_code=?,retry_condition=?,finished_at=?,updated_at=? WHERE id=? AND state IN ('QUEUED','RUNNING') AND (? IS NULL OR owner=?)",(state,'Finished' if state=='COMPLETED' else 'Agent reconciliation required',error,retry,now(),now(),identifier,owner,owner)).rowcount
            if count:
                self.event(conn,identifier,state,{'error_code':error})
                if state!='COMPLETED':
                    work=conn.execute('SELECT batch_id,application_ids FROM browser_workflows WHERE id=?',(identifier,)).fetchone()
                    if work['batch_id']:conn.execute("UPDATE browser_batches SET status='ERROR',finished_at=?,error_code=? WHERE id=?",(now(),error,work['batch_id']))
                    for application_id in json.loads(work['application_ids']):
                        conn.execute("UPDATE browser_applications SET state=CASE WHEN application_outcome='NOT_SUBMITTED' THEN 'ERROR' ELSE application_outcome END,preparation_state='ERROR',phase='Worker failed; progress preserved',retry_condition=?,updated_at=? WHERE id=? AND preparation_state='PREPARING'",(retry,now(),application_id))
                        conn.execute("UPDATE browser_operations SET state='UNCERTAIN',error_code='worker_interrupted',next_action=?,updated_at=? WHERE application_id=? AND kind LIKE 'upload:%' AND state='PENDING'",(retry,now(),application_id))
        if state=='COMPLETED':
            from .orchestration import dispatch_pending_resumes
            dispatch_pending_resumes(self.db)

    def recover_expired(self,at=None):
        stamp=at or now();recovered=[]
        with self.db.transaction() as conn:
            conn.execute('BEGIN IMMEDIATE')
            rows=[dict(r) for r in conn.execute("SELECT * FROM browser_workflows WHERE state IN ('QUEUED','RUNNING') AND lease_until<=?",(stamp,))]
            for row in rows:
                retry='Read-only reconciliation required; do not retry uncertain external writes.'
                conn.execute("UPDATE browser_workflows SET state='INTERRUPTED',phase='Worker heartbeat expired',error_code='worker_lease_expired',retry_condition=?,finished_at=?,updated_at=? WHERE id=?",(retry,stamp,stamp,row['id']))
                if row['batch_id']:conn.execute("UPDATE browser_batches SET status='ERROR',error_code='worker_lease_expired',finished_at=? WHERE id=?",(stamp,row['batch_id']))
                for identifier in json.loads(row['application_ids']):
                    # Fence any in-flight upload before permitting a future read-only reconciliation.
                    conn.execute("UPDATE browser_operations SET state='UNCERTAIN',error_code='worker_interrupted',next_action=?,updated_at=? WHERE application_id=? AND kind LIKE 'upload:%' AND state='PENDING'",(retry,stamp,identifier))
                    app=conn.execute('SELECT * FROM browser_applications WHERE id=?',(identifier,)).fetchone()
                    if app and app['preparation_state']=='PREPARING':
                        state=app['application_outcome'] if app['application_outcome']!='NOT_SUBMITTED' else 'ERROR'
                        conn.execute("UPDATE browser_applications SET preparation_state='ERROR',state=?,phase='Worker interrupted; progress preserved',retry_condition=?,updated_at=? WHERE id=?",(state,retry,stamp,identifier))
                self.event(conn,row['id'],'INTERRUPTED',{'error_code':'worker_lease_expired','cursor':row['cursor']});recovered.append(row['id'])
        return recovered

    def list(self):
        with self.db.transaction() as conn:ids=[r[0] for r in conn.execute('SELECT id FROM browser_workflows ORDER BY created_at DESC LIMIT 20')]
        return [self.get(identifier) for identifier in ids]

    @contextmanager
    def running(self,identifier):
        owner=self.claim(identifier);stop=threading.Event()
        def tick():
            while not stop.wait(min(3,self.lease_seconds/3)):
                try:
                    if not self.heartbeat(identifier,owner):break
                except Exception:break  # Ownership expires; next write is fenced.
        thread=threading.Thread(target=tick,name='browser-heartbeat',daemon=True);thread.start()
        try:yield owner
        except BaseException:
            self.finish(identifier,'ERROR','worker_interrupted_or_failed',owner);raise
        else:self.finish(identifier,owner=owner)
        finally:stop.set();thread.join(timeout=5)


def fair_applications(db,identifier=None):
    rows=BrowserStore(db).list(include_history=True)
    if identifier:return [r for r in rows if r['id']==identifier]
    with db.transaction() as conn:scores={r['job_id']:r['fit'] for r in conn.execute('SELECT job_id,fit FROM application_priority')}
    return sorted((r for r in rows if r['preparation_state']!='PREPARING' or r['session_health']=='LOST'),key=lambda r:(r['last_sync_at'] or '',-scores.get(r['job_id'],0),r['updated_at'],r['id']))[:5]

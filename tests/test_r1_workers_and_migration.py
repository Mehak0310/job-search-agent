import hashlib,json,sqlite3,time
from datetime import datetime,timedelta,timezone
from pathlib import Path
import pytest
from job_agent.browser_workers import BrowserWorkers
from job_agent.browser_store import BrowserStore
from job_agent.migrations import migrate_v16
from job_agent.application_state import submission_projection
from job_agent.review_queue import hidden_job_ids
from job_agent.requirements import assess_requirements
from job_agent import browser_applications as runner
from tests.test_browser_applications import prepared_store


def test_additive_upgrade_restores_lost_report_from_append_only_history(tmp_path):
    path=tmp_path/'legacy.sqlite3';c=sqlite3.connect(path)
    c.executescript('''CREATE TABLE browser_batches(id TEXT PRIMARY KEY,status TEXT,created_at TEXT,finished_at TEXT,error_code TEXT);
    CREATE TABLE browser_applications(id TEXT PRIMARY KEY,batch_id TEXT,job_id TEXT,identity TEXT,url TEXT,ats TEXT,state TEXT,target_id TEXT,session_id TEXT,inspection TEXT DEFAULT '{}',missing TEXT DEFAULT '[]',checks TEXT DEFAULT '[]',documents TEXT DEFAULT '[]',updated_at TEXT,confirmation_ref TEXT);
    CREATE TABLE browser_events(id INTEGER PRIMARY KEY,application_id TEXT,event TEXT,details TEXT,created_at TEXT);
    CREATE TABLE preserved_user_edits(id TEXT PRIMARY KEY,body TEXT);
    INSERT INTO preserved_user_edits VALUES('original','Never overwrite this edit');
    INSERT INTO browser_batches VALUES('batch','REVIEW','2026-10-18',NULL,NULL);
    PRAGMA user_version=15;''')
    for identifier,state,reference in [('reported','SESSION_LOST',None),('closed','SESSION_LOST',None),('confirmed','SUBMISSION_CONFIRMED','browser-confirmation:'+'a'*64)]:
        c.execute("INSERT INTO browser_applications(id,batch_id,job_id,identity,url,ats,state,updated_at,confirmation_ref) VALUES(?,'batch',?,?,?,'greenhouse',?,'2026-10-18',?)",(identifier,identifier,identifier,'https://example.com/'+identifier,state,reference))
    c.execute("INSERT INTO browser_events(application_id,event,details) VALUES('reported','STATE_CHECKPOINT',?)",(json.dumps({'state':'USER_REPORTED_SUBMITTED'}),));c.commit()
    old_events=c.execute('SELECT * FROM browser_events').fetchall();migrate_v16(c,path)
    assert c.execute('PRAGMA user_version').fetchone()[0]==16
    assert c.execute("SELECT application_outcome,session_health FROM browser_applications WHERE id='reported'").fetchone()==('USER_REPORTED_SUBMITTED','LOST')
    assert c.execute("SELECT application_outcome FROM browser_applications WHERE id='closed'").fetchone()[0]=='NOT_SUBMITTED'
    assert c.execute("SELECT application_outcome FROM browser_applications WHERE id='confirmed'").fetchone()[0]=='SUBMISSION_CONFIRMED'
    assert c.execute('SELECT * FROM browser_events').fetchall()==old_events
    assert c.execute('SELECT body FROM preserved_user_edits').fetchone()[0]=='Never overwrite this edit'
    with sqlite3.connect(path.with_suffix('.sqlite3.pre-v16.bak')) as old:
        assert old.execute('PRAGMA user_version').fetchone()[0]==15
        assert old.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    c.close()


def test_verified_requisition_alias_uses_same_outcome_projection(tmp_path):
    store,_,key=prepared_store(tmp_path);app=store.batch([key],1)['applications'][0]
    store.update(app['id'],state='USER_REPORTED_SUBMITTED')
    with store.db.transaction() as conn:
        original=dict(conn.execute('SELECT * FROM jobs WHERE id=?',(key,)).fetchone())
        alias={**original,'id':'verified-alias','identity_key':'verified-alias-identity','application_url':'https://example.com/received-alert','canonical_application_url':original['application_url']}
        conn.execute('INSERT INTO jobs('+','.join(alias)+') VALUES('+','.join('?' for _ in alias)+')',tuple(alias.values()))
        assert submission_projection(conn,'verified-alias')['application_outcome']=='USER_REPORTED_SUBMITTED'
    assert 'verified-alias' in hidden_job_ids(store.db)


def test_live_heartbeat_advances_and_failure_has_durable_terminal_state(tmp_path):
    store,_,key=prepared_store(tmp_path);batch=store.batch([key],1);identifier=batch['applications'][0]['id']
    workers=BrowserWorkers(store.db,lease_seconds=1)
    operation=workers.enqueue('PREPARE',[identifier],batch['batch_id'])
    with pytest.raises(RuntimeError,match='parser'):
        with workers.running(operation) as owner:
            before=workers.get(operation)['heartbeat_at'];time.sleep(.45)
            assert workers.get(operation)['heartbeat_at']>before
            workers.checkpoint(operation,owner,0,'Inspecting fixture')
            raise RuntimeError('fixture parser defect; never retry blindly')
    assert workers.get(operation)['state']=='ERROR'
    assert workers.get(operation)['retry_condition']


def test_expired_queued_worker_and_invalid_transitions_fail_closed(tmp_path):
    store,_,key=prepared_store(tmp_path);identifier=store.batch([key],1)['applications'][0]['id']
    workers=BrowserWorkers(store.db);operation=workers.enqueue('SYNC',[identifier])
    with store.db.transaction() as conn:conn.execute("UPDATE browser_workflows SET lease_until='2000-01-01' WHERE id=?",(operation,))
    with pytest.raises(ValueError,match='lease_unavailable'):workers.claim(operation)
    workers.recover_expired();assert workers.get(operation)['state']=='INTERRUPTED'
    with pytest.raises(ValueError,match='terminal'):workers.finish(operation,'SAVED')
    with pytest.raises(ValueError,match='not_found'):workers.get('missing')


def test_controller_launch_failure_cannot_leave_permanent_queued_batch(tmp_path,monkeypatch):
    store,_,key=prepared_store(tmp_path);batch=store.batch([key],1)
    def unavailable(*args,**kwargs):raise OSError('fixture process creation failed')
    monkeypatch.setattr(runner.subprocess,'Popen',unavailable)
    with pytest.raises(ValueError,match='launch_failed'):runner.launch_worker(store.db,batch['batch_id'])
    workers=BrowserWorkers(store.db);assert workers.list()[0]['state']=='ERROR'
    with store.db.transaction() as conn:assert conn.execute('SELECT status FROM browser_batches WHERE id=?',(batch['batch_id'],)).fetchone()[0]=='ERROR'
    assert store.get(batch['applications'][0]['id'])['preparation_state']=='ERROR'


def test_default_profile_skill_lists_are_not_verified_candidate_evidence():
    verdict=assess_requirements({'employment_skills':['react'],'reviewed':False},{'required_skills':['react']})
    assert verdict['state']=='UNKNOWN'
    approved={'employment_skills':['react'],'skill_evidence':{'react':[{'source':'explicit accepted fixture fact'}]}}
    from tests.test_requirement_completeness import full_job
    assert assess_requirements(approved,full_job('Requirements\nReact required.'))['state']=='PASS'


def test_reconstruction_resets_preparation_without_erasing_submission_history(tmp_path):
    store,_,key=prepared_store(tmp_path)
    app=store.batch([key],1)['applications'][0]
    store.update(app['id'],state='NEEDS_USER_ANSWER')
    store.update(app['id'],state='SESSION_LOST')
    restored=store.batch([key],1,reconstruct=True)['applications'][0]
    assert restored['preparation_state']=='PREPARING'
    assert restored['session_health']=='UNKNOWN'
    store.update(app['id'],state='USER_REPORTED_SUBMITTED')
    store.update(app['id'],state='SESSION_LOST')
    assert store.batch([key],1,reconstruct=True)['selected']==0

import json
import pytest
from job_agent.priority_queue import refresh,candidates,classify_message,record_message,snapshot
from job_agent.m2d_models import EmailExportMessage
from job_agent.models import JobInput
from job_agent.m3_models import ContactInput
from job_agent.service import JobService
from job_agent.m2d import M2DEngine
from job_agent.browser_store import BrowserStore
from tests.test_r2 import ready
from tests.test_browser_applications import approve_requirements


def jobs(tmp_path,scores=(95,90,85,80,75,10)):
    db,engine,first=ready(tmp_path);service=JobService(db)
    with db.transaction() as c:c.execute("UPDATE jobs SET application_url='https://job-boards.greenhouse.io/example/jobs/100',canonical_application_url='https://job-boards.greenhouse.io/example/jobs/100'")
    approve_requirements(db,first['job_id']);ids=[first['job_id']]
    for index,score in enumerate(scores[1:],101):
        service.import_rows([JobInput(source='priority-fixture',source_job_id=str(index),company='Example Corp',title='Frontend '+str(index),location='Noida',description='React required.',skills=['react'],work_mode='hybrid',application_url='https://job-boards.greenhouse.io/example/jobs/'+str(index),is_sample=True)])
    M2DEngine(db).sync_existing_jobs()
    with db.transaction() as c:ids += [r[0] for r in c.execute('SELECT id FROM jobs WHERE id<>? ORDER BY title',(first['job_id'],))]
    for identifier,score in zip(ids,scores):
        approve_requirements(db,identifier)
        with db.transaction() as c:c.execute('UPDATE jobs SET match_score=? WHERE id=?',(score,identifier))
        engine.prepare(identifier)
    return db,engine,ids


def test_actual_persisted_selection_is_fit_descending_and_worker_order_is_reserved(tmp_path):
    db,_,ids=jobs(tmp_path);refresh(db)
    assert [r['fit'] for r in candidates(db)]==[95,90,85,80,75]
    batch=BrowserStore(db).batch(limit=5)
    with db.transaction() as c:rows=list(c.execute('SELECT job_id,fit,reserved_order,attempts FROM application_priority WHERE batch_id=? ORDER BY reserved_order',(batch['batch_id'],)))
    assert [r['fit'] for r in rows]==[95,90,85,80,75] and all(r['attempts']==1 for r in rows)
    assert len({r['job_id'] for r in rows})==5
    assert BrowserStore(db).batch(ids[:5],5)['selected']==0


def test_unknown_and_failed_eligibility_never_enter_preparation(tmp_path):
    db,_,ids=jobs(tmp_path)
    with db.transaction() as c:
        c.execute("UPDATE job_operational_state SET headcount_state='UNKNOWN' WHERE job_id=?",(ids[0],))
        c.execute("UPDATE job_operational_state SET india_state='FAIL' WHERE job_id=?",(ids[1],))
        c.execute("UPDATE jobs SET discovery_detail='{}' WHERE id=?",(ids[2],))
    state=refresh(db);assert all(r['job_id'] not in ids[:3] for r in candidates(db))
    assert BrowserStore(db).batch(ids[:3],3)['selected']==0
    assert next(r for r in state['items'] if r['job_id']==ids[0])['state']=='VERIFICATION'


def test_stable_ties_and_deadline_then_freshness(tmp_path):
    db,_,ids=jobs(tmp_path,(90,90,90))
    with db.transaction() as c:
        c.execute('UPDATE jobs SET published_at=NULL')
    refresh(db);assert [r['job_id'] for r in candidates(db)]==sorted(ids)
    with db.transaction() as c:c.execute("UPDATE jobs SET published_at='2026-10-19T00:00:00Z' WHERE id=?",(ids[-1],))
    refresh(db);assert candidates(db)[0]['job_id']==ids[-1]


@pytest.mark.parametrize('subject,body,sender,category,tier',[
 ('New job alert: urgent interview','Please reply today. Unsubscribe from alerts.','jobs@naukri.com','AUTOMATED_JOB_ALERT',0),
 ('Interview availability','Please reply by 2026-10-20 with your availability.','ria@company.test','INTERVIEW_REQUEST',3),
 ('Screening assessment','Please complete the screening assessment.','talent@company.test','SCREENING_QUESTIONS',2),
 ('Next steps','Please reply with your CV today.','recruiter@company.test','DIRECT_RECRUITER_ACTION',3),
 ('Following up','Recruiter following up on a role.','ria@company.test','RECRUITER_FOLLOW_UP',1),
])
def test_recruiter_actions_and_alerts_are_distinct(subject,body,sender,category,tier):
    m=EmailExportMessage(message_id='message',received_at='2026-10-19T00:00:00Z',subject=subject,body=body,sender=sender)
    result=classify_message(m);assert result['category']==category and result['tier']==tier


def test_verified_recruiter_link_gets_explicit_priority_and_pending_recalculates(tmp_path):
    db,engine,ids=jobs(tmp_path)
    message=EmailExportMessage(message_id='urgent',received_at='2026-10-19T00:00:00Z',subject='Interview',body='Please reply by 2026-10-20 with availability.',sender='ria@company.test')
    record_message(db,message)
    engine.add_contact(ids[-1],ContactInput(name='Recruiter',employer='Example Corp',email='ria@company.test',source_message_id='urgent',role_relevance='Verified recruiter for this role',verification_status='VERIFIED'))
    refresh(db);assert candidates(db)[0]['job_id']==ids[-1]
    assert 'Verified recruiter-linked' in candidates(db)[0]['reason']
    batch=BrowserStore(db).batch([ids[-1]],1)
    with db.transaction() as c:c.execute('UPDATE jobs SET match_score=1 WHERE id=?',(ids[-1],))
    refresh(db)
    with db.transaction() as c:r=c.execute('SELECT * FROM application_priority WHERE job_id=?',(ids[-1],)).fetchone()
    assert r['state']=='RESERVED' and r['batch_id']==batch['batch_id'] and r['fit']==10


def test_fairness_slot_and_submission_history_are_persistent(tmp_path):
    db,_,ids=jobs(tmp_path);refresh(db)
    with db.transaction() as c:c.execute('UPDATE application_priority SET skips=3 WHERE job_id=?',(ids[-1],))
    chosen=candidates(db);assert chosen[-1]['job_id']==ids[-1] and 'Fairness slot' in chosen[-1]['reason']
    with db.transaction() as c:c.execute("UPDATE jobs SET status='SUBMITTED' WHERE id=?",(ids[0],))
    refresh(db);assert ids[0] not in [r['job_id'] for r in candidates(db)]
    assert snapshot(db)['pending']==5


def test_interrupted_reservation_does_not_automatically_retry(tmp_path):
    from job_agent.browser_workers import BrowserWorkers
    db,_,ids=jobs(tmp_path);batch=BrowserStore(db).batch([ids[0]],1)
    workers=BrowserWorkers(db);identifier=workers.enqueue('PREPARE',[batch['applications'][0]['id']],batch['batch_id']);workers.finish(identifier,'INTERRUPTED','synthetic interruption')
    refresh(db);refresh(db)
    with db.transaction() as c:row=c.execute('SELECT * FROM application_priority WHERE job_id=?',(ids[0],)).fetchone()
    assert row['state']=='REVIEW_REQUIRED' and row['attempts']==1
    assert BrowserStore(db).batch([ids[0]],1)['selected']==0


def test_new_verified_gate_evidence_recalculates_pending_without_manual_refresh(tmp_path):
    from job_agent.m2d_models import OperationalFacts
    db,_,ids=jobs(tmp_path);refresh(db)
    M2DEngine(db).set_operational_state(ids[0],OperationalFacts(active='PASS',india_eligible='PASS',headcount='UNKNOWN',direct_permanent_payroll='PASS',mandatory_requirements='PASS'),job_id=ids[0])
    with db.transaction() as c:assert c.execute('SELECT state FROM application_priority WHERE job_id=?',(ids[0],)).fetchone()[0]=='VERIFICATION'

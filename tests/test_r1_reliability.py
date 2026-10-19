import json
import sqlite3
from datetime import datetime,timedelta,timezone
import pytest
from job_agent import browser_applications as runner
from job_agent.application_answers import answer,question_key
from job_agent.application_state import submission_projection
from job_agent.browser_forms import Dispatcher,inventory
from job_agent.browser_store import BrowserStore
from job_agent.browser_workers import BrowserWorkers,fair_applications
from job_agent.requirements import assess_requirements
from job_agent.review_queue import hidden_job_ids
from job_agent.review_workflow import progress
from job_agent.service import JobService
from tests.test_browser_applications import prepared_store,frame,browser


def test_exact_submission_loss_regression_survives_switch_restart_and_alias(tmp_path,monkeypatch):
    store,engine,key=prepared_store(tmp_path);app=store.batch([key],1)['applications'][0]
    store.update(app['id'],state='USER_REPORTED_SUBMITTED')
    def missing():raise OSError('fixture offline')
    monkeypatch.setattr(runner,'browser_metadata',missing)
    assert runner.switch_tab(store.db,app['id'])['state']=='SESSION_LOST'  # Session result only.
    restarted=BrowserStore(store.db);row=restarted.get(app['id'])
    assert row['state']==row['application_outcome']=='USER_REPORTED_SUBMITTED'
    assert row['session_health']=='LOST' and key in hidden_job_ids(store.db)
    assert restarted.list()==[]
    assert restarted.list(include_history=True)[0]['submission_verified'] is False
    with store.db.transaction() as conn:
        summary=submission_projection(conn,key)
        assert 'manually' in summary['submission_label']
    job=JobService(store.db).get_job(key);assert job['application_outcome']=='USER_REPORTED_SUBMITTED'
    assert engine.get(engine.by_job(key)['packet_id'])['application_outcome']=='USER_REPORTED_SUBMITTED'
    with pytest.raises(ValueError,match='submission_history'):restarted.job(key)


def test_confirmed_outcome_cannot_downgrade_and_needs_evidence(tmp_path):
    store,_,key=prepared_store(tmp_path);identifier=store.batch([key],1)['applications'][0]['id']
    with pytest.raises(ValueError,match='evidence_required'):store.update(identifier,state='SUBMISSION_CONFIRMED')
    from job_agent.document_manifest import sha256
    path=runner.root_for(store.db)/(identifier+'-confirmation.png');path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'synthetic confirmation evidence')
    reference='browser-confirmation:'+sha256(path)
    store.update(identifier,state='SUBMISSION_CONFIRMED',confirmation_ref=reference)
    for state in ['SESSION_LOST','ERROR','PREPARING','USER_REPORTED_SUBMITTED']:
        store.update(identifier,state=state)
        assert store.get(identifier)['application_outcome']=='SUBMISSION_CONFIRMED'
    assert key in hidden_job_ids(store.db)
    with store.db.transaction() as conn:assert submission_projection(conn,key)['submission_verified']


@pytest.mark.parametrize('profile,job,expected',[
    ({'professional_skills':['angular']},{'required_skills':['angular']},'UNKNOWN'),
    ({'professional_skills':['angular']},{'required_skills':['kubernetes']},'UNKNOWN'),
    ({'project_skills':['rag'],'professional_ai_confirmed':True},{'required_skills':['rag']},'UNKNOWN'),
    ({'professional_skills':['rag'],'professional_ai_confirmed':True},{'required_skills':['rag'],'required_experience_min':3,'experience_scope':'ai'},'UNKNOWN'),
    ({'professional_skills':['angular'],'total_experience_years':7.1,'reviewed':True},{'required_skills':['angular'],'required_experience_min':7.2,'experience_scope':'total'},'FAIL'),
    ({'professional_skills':['angular'],'total_experience_years':9},{'required_skills':['angular'],'required_experience_min':8,'required_experience_max':5},'CONFLICT'),
])
def test_requirement_verdicts_do_not_infer_capability_or_round_tenure(profile,job,expected):
    assert assess_requirements(profile,job)['state']==expected


def test_requirement_conflicting_sourced_decisions_and_ambiguous_tenure():
    profile={'professional_skills':['angular'],'total_experience_years':10}
    job={'required_skills':['angular'],'required_experience_min':5,'experience_scope':'total','description':'5 years relevant experience'}
    assert assess_requirements(profile,job)['state']=='UNKNOWN'
    evidence=[{'kind':'mandatory_requirements','verified_at':'2026-10-18','evidence_url':'https://example.com/'+s,'state':s} for s in ['PASS','FAIL']]
    assert assess_requirements(profile,{'required_skills':['angular']},evidence)['state']=='CONFLICT'


@pytest.mark.parametrize('label',[
    'I confirm the information provided in this application is complete',
    'I certify the answers above','I acknowledge','I agree',
    'The statements and answers above are accurate and true',
    'By continuing, you authorize processing of your personal data',
    'Allow us to share your personal details with third parties',
])
def test_declaration_guard_precedes_saved_answers_and_dispatch(frame,label):
    frame.set_content('<label id="label"><input id="statement"></label>')
    frame.locator('#label').evaluate('(e,t)=>e.prepend(document.createTextNode(t))',label)
    field=inventory(frame)[0];key=question_key(label,'Example')
    assert answer(field,{key:'Yes'}, {},'','Role','Example')==(None,None)
    with pytest.raises(ValueError,match='attestation'):Dispatcher(frame).act('FILL',field,'Yes')
    # Even a stale/inaccurate field label cannot turn a declaration into contact data.
    with pytest.raises(ValueError,match='attestation'):Dispatcher(frame).act('FILL',{**field,'label':'Email'},'Yes')
    assert frame.locator('#statement').input_value()==''


def test_contact_confirmation_remains_factual_and_structural_legal_control_is_manual(frame):
    f={'label':'Please confirm your email address','type':'email'}
    assert answer(f,{'email':'fixture@example.com'}, {},'','Role','Example')[0]=='fixture@example.com'
    frame.set_content('<div data-attestation><label>Verification<input id="v"></label></div>')
    with pytest.raises(ValueError,match='attestation'):Dispatcher(frame).act('FILL',inventory(frame)[0],'Yes')


def test_worker_lease_cursor_fencing_and_uncertain_upload_recovery(tmp_path):
    store,_,key=prepared_store(tmp_path);batch=store.batch([key],1);identifier=batch['applications'][0]['id']
    workers=BrowserWorkers(store.db);operation=workers.enqueue('PREPARE',[identifier],batch['batch_id'])
    with pytest.raises(ValueError,match='already_running'):workers.enqueue('SYNC',[identifier])
    owner=workers.claim(operation);workers.checkpoint(operation,owner,1,'Checking upload')
    assert workers.heartbeat(operation,owner)
    with pytest.raises(ValueError,match='ownership_lost'):workers.assert_owner(operation,'other-owner')
    opid,_=store.begin_operation(identifier,'upload:resume','immutable-hash',write=True)
    future=(datetime.now(timezone.utc)+timedelta(minutes=2)).isoformat()
    assert workers.recover_expired(future)==[operation] and workers.recover_expired(future)==[]
    row=workers.get(operation);assert row['state']=='INTERRUPTED' and row['cursor']==1
    assert store.get(identifier)['preparation_state']=='ERROR'
    with store.db.transaction() as conn:assert conn.execute('SELECT state FROM browser_operations WHERE id=?',(opid,)).fetchone()[0]=='UNCERTAIN'
    with pytest.raises(ValueError,match='uncertain'):store.begin_operation(identifier,'upload:resume','immutable-hash',write=True)
    assert not workers.heartbeat(operation,owner)
    assert progress(store.db)['operations'][0]['state']=='INTERRUPTED'


def test_server_discovers_batch_without_session_storage_and_terminal_owner_is_fenced(tmp_path):
    store,_,key=prepared_store(tmp_path);batch=store.batch([key],1);identifier=batch['applications'][0]['id']
    workers=BrowserWorkers(store.db);operation=workers.enqueue('PREPARE',[identifier],batch['batch_id'])
    with workers.running(operation) as owner:
        data=progress(store.db)
        assert data['active_batch_id']==batch['batch_id'] and data['work_active']
        store.update(identifier,inspection={'stage':'Filling saved answers','answered':3})
        assert store.list()[0]['completed_fields']==3
    assert workers.get(operation)['state']=='COMPLETED'
    with pytest.raises(ValueError,match='ownership_lost'):workers.assert_owner(operation,owner)


def test_fair_sync_selection_advances_after_failed_or_lost_sessions(tmp_path):
    store,_,key=prepared_store(tmp_path);first=store.batch([key],1)['applications'][0]
    # Additional synthetic records use independent requisition identities.
    with store.db.transaction() as conn:
        original=dict(conn.execute('SELECT * FROM browser_applications WHERE id=?',(first['id'],)).fetchone())
        for i in range(1,8):
            value={**original,'id':'fair-'+str(i),'identity':'fair-identity-'+str(i),'updated_at':'2020-01-01'}
            conn.execute('INSERT INTO browser_applications('+','.join(value)+') VALUES('+','.join('?' for _ in value)+')',tuple(value.values()))
    for row in store.list():store.update(row['id'],state='SESSION_LOST')
    first_five=fair_applications(store.db)
    for row in first_five:store.update(row['id'],last_sync_at='2026-10-18T10:00:00+00:00')
    next_five=fair_applications(store.db)
    assert len({r['id'] for r in first_five}|{r['id'] for r in next_five})==8

"""R2 end-to-end local persistence and fake-only draft approval regression."""
import json,sqlite3
import pytest
from fastapi.testclient import TestClient
from job_agent.application_answers import approved_facts
from job_agent.fact_memory import record,resolve,projection
from job_agent.service import JobService
from job_agent.reconciliation_r2 import reconcile
from job_agent.draft_review import preview,approve
from job_agent.m3_models import PacketEdit,EmployerQuestion
from job_agent.main import create_app
from tests.test_preparation_authorizations import setup_authorized
from tests.test_automatic_drafts import Adapter


def ready(tmp_path):
    db,engine,packet,*_=setup_authorized(tmp_path)
    import zipfile
    bank=tmp_path/'Answer_Bank.docx'
    with zipfile.ZipFile(bank,'w') as z:z.writestr('word/document.xml','<document/>')
    from job_agent.document_manifest import sha256
    manifest=json.loads(engine.manifest_path.read_text())
    for item in manifest['documents']:
        if item['canonical_name']==bank.name:item['sha256']=sha256(bank)
    engine.manifest_path.write_text(json.dumps(manifest))
    with db.transaction() as c:c.execute("UPDATE job_operational_state SET active_state='PASS',india_state='PASS',headcount_state='PASS',payroll_state='PASS'")
    from tests.test_browser_applications import approve_requirements
    approve_requirements(db,packet['job_id'])
    return db,engine,packet


def test_known_confirmed_profile_facts_are_resolved_without_document_parse(tmp_path):
    db,_,_=ready(tmp_path)
    profile,facts,sources,_=approved_facts(db)
    assert facts['notice_period']=='45 days; not serving'
    assert sources['notice_period']['resolution']=='RESOLVED'
    JobService(db).record_confirmed_application_answers({'country':'India'},'Explicit synthetic current confirmation')
    assert approved_facts(db)[1]['country']=='India'


def test_verified_correction_supersedes_retaining_history(tmp_path):
    db,_,_=ready(tmp_path);service=JobService(db)
    service.record_confirmed_application_answers({'country':'First'},'first synthetic confirmation')
    service.record_confirmed_application_answers({'country':'Second'},'verified synthetic correction')
    assert approved_facts(db)[1]['country']=='Second'
    with db.transaction() as c:
        rows=[dict(r) for r in c.execute("SELECT * FROM fact_memory WHERE field_key='country'")]
        assert len(rows)==2 and any(json.loads(r['supersedes']) for r in rows)
        with pytest.raises(sqlite3.IntegrityError):c.execute("UPDATE fact_memory SET value='tamper'")


def test_same_priority_conflict_remains_unknown(tmp_path):
    db,_,_=ready(tmp_path)
    with db.transaction() as c:
        record(c,'country','One',source='approved fixture A',version=1)
        record(c,'country','Two',source='approved fixture B',version=1)
    assert 'country' not in approved_facts(db)[1]
    assert approved_facts(db)[2]['country']['resolution']=='CONFLICT'
    assert resolve([])['state']=='UNKNOWN'
    with pytest.raises(ValueError):
        with db.transaction() as c:record(c,'country','',source='fixture',version=1)


def test_employer_scoped_evidence_does_not_transfer(tmp_path):
    db,_,_=ready(tmp_path)
    with db.transaction() as c:record(c,'prior_work','No',source='explicit employer fixture',version=1,scope='employer:example')
    assert 'prior_work' not in projection(db,{}, {}, {},'Other')
    assert projection(db,{}, {}, {},'Example')['prior_work']['value']=='No'


@pytest.mark.parametrize('edited',[False,True])
def test_packet_reconciliation_preserves_manual_text_history_and_is_idempotent(tmp_path,edited):
    db,engine,p=ready(tmp_path)
    if edited:
        v=p['version_data'];p=engine.edit(p['packet_id'],PacketEdit(subject='MY exact subject',email_text='MY exact email',email_html='<p>MY exact email</p>',supporting_statement='MY exact statement'))
    before=engine.get(p['packet_id'])
    JobService(db).record_confirmed_application_answers({'country':'India'},'synthetic profile update')
    result=reconcile(db);after=engine.get(p['packet_id'])
    assert result['revised_packets']==1 and after['profile_version']>before['profile_version']
    if edited:
        for key in ['subject','email_text','email_html','supporting_statement']:assert after['version_data'][key]==before['version_data'][key]
    with db.transaction() as c:
        assert c.execute('SELECT email_text FROM application_packet_versions WHERE packet_id=? AND version=?',(p['packet_id'],before['current_version'])).fetchone()[0]==before['version_data']['email_text']
    assert reconcile(db)['revised_packets']==0


def test_browser_missing_inventory_reconciles_without_filling_or_claiming_ready(tmp_path):
    from tests.test_browser_applications import prepared_store
    from job_agent.review_workflow import pending_questions,resolution_report
    store,_,key=prepared_store(tmp_path);app=store.batch([key],1)['applications'][0]
    root=store.db.path.parent/'browser-applications';root.mkdir(exist_ok=True)
    inventory={'inventory':[{'id':'country','label':'Country','type':'text','required':True,'visible':True,'value':''},{'id':'consent','label':'I confirm these answers are accurate','type':'checkbox','required':True,'visible':True,'value':False},{'id':'missing','label':'Years in unusual domain','type':'text','required':True,'visible':True,'value':''}]}
    path=root/(app['id']+'.json');path.write_text(json.dumps(inventory));raw=path.read_bytes()
    JobService(store.db).record_confirmed_application_answers({'country':'India'},'synthetic confirmation')
    reconcile(store.db)
    assert len(pending_questions(store.db,app['id']))==1
    report=resolution_report(store.db,app['id']);assert report['fields'][0]['state']=='RESOLVED' and report['fields'][1]['state']=='HUMAN_ONLY'
    assert json.loads(store.get(app['id'])['missing'])==['Years in unusual domain']
    assert store.get(app['id'])['state']!='READY_FOR_USER_REVIEW' and path.read_bytes()==raw
    inventory['stale']=True;path.write_text(json.dumps(inventory))
    assert all(f['state']=='NEEDS_INSPECTION' for f in resolution_report(store.db,app['id'])['fields'])


def test_exact_preview_approved_fake_draft_stores_id_and_never_repeats(tmp_path):
    db,engine,p=ready(tmp_path);adapter=Adapter(db);adapter.isolated_test_adapter=True
    shown=preview(db,p['packet_id']);assert not shown['blockers']
    assert shown['text']==engine.get(p['packet_id'])['version_data']['email_text']
    assert shown['recipient']=='ria@example.com' and shown['recipient_evidence']['source_url']
    assert shown['preview_id']==preview(db,p['packet_id'])['preview_id']
    saved=approve(db,shown['preview_id'],adapter,approved=True)
    assert saved['gmail_draft_id']=='synthetic-unsent-draft' and '/#drafts/' in saved['gmail_url']
    with pytest.raises(ValueError,match='existing_draft'):approve(db,shown['preview_id'],adapter,approved=True)
    assert len(adapter.calls)==1
    with db.transaction() as c:assert c.execute('SELECT gmail_draft_id FROM gmail_draft_operations').fetchone()[0]==saved['gmail_draft_id']


@pytest.mark.parametrize('change',['recipient','headcount','india','payroll','closed','unrelated'])
def test_preview_blocks_unsafe_recipient_and_eligibility(tmp_path,change):
    db,_,p=ready(tmp_path)
    with db.transaction() as c:
        if change=='recipient':c.execute("UPDATE contact_evidence SET verification_status='UNVERIFIED'")
        elif change=='unrelated':c.execute("UPDATE contact_evidence SET email='privacy@example.com'")
        elif change=='closed':c.execute("UPDATE job_operational_state SET lifecycle='CLOSED'")
        else:c.execute('UPDATE job_operational_state SET '+change+"_state='FAIL'")
    shown=preview(db,p['packet_id']);assert shown['blockers']
    adapter=Adapter(db);adapter.isolated_test_adapter=True
    with pytest.raises(ValueError,match='draft_blocked'):approve(db,shown['preview_id'],adapter,approved=True)
    assert adapter.calls==[]


def test_exact_approval_change_and_live_adapter_are_rejected(tmp_path):
    db,engine,p=ready(tmp_path);shown=preview(db,p['packet_id']);adapter=Adapter(db);adapter.isolated_test_adapter=True
    with pytest.raises(ValueError,match='explicit'):approve(db,shown['preview_id'],adapter)
    with pytest.raises(ValueError,match='r2_live_drafts_disabled'):approve(db,shown['preview_id'],object(),approved=True)
    v=p['version_data'];engine.edit(p['packet_id'],PacketEdit(subject='Changed',email_text=v['email_text'],email_html=v['email_html'],supporting_statement=v['supporting_statement']))
    with pytest.raises(ValueError,match='preview_changed'):approve(db,shown['preview_id'],adapter,approved=True)
    with pytest.raises(ValueError,match='not_found'):approve(db,'0'*64,adapter,approved=True)
    assert adapter.calls==[]


def test_uncertain_fake_draft_never_automatically_retries(tmp_path):
    db,_,p=ready(tmp_path);adapter=Adapter(db,fail=True);adapter.isolated_test_adapter=True
    shown=preview(db,p['packet_id'])
    with pytest.raises(ValueError,match='uncertain'):approve(db,shown['preview_id'],adapter,approved=True)
    with pytest.raises(ValueError,match='existing_draft'):approve(db,shown['preview_id'],adapter,approved=True)
    assert len(adapter.calls)==1


def test_approval_http_uses_persisted_content_and_fake_adapter(tmp_path):
    db,_,p=ready(tmp_path);app=create_app(db.path);fake=Adapter(db);fake.isolated_test_adapter=True;app.state.r2_draft_adapter=fake
    with TestClient(app) as client:
        shown=client.post('/api/m3/packets/'+p['packet_id']+'/draft-preview').json()
        response=client.post('/api/m3/draft-approvals',json={'preview_id':shown['preview_id'],'approved':True})
        assert response.status_code==200 and response.json()['gmail_draft_id']=='synthetic-unsent-draft'
        assert client.post('/api/m3/draft-approvals',json={'preview_id':shown['preview_id'],'approved':True}).status_code==409
        assert client.post('/api/m3/packets/missing/draft-preview').status_code==422


def test_received_metadata_and_duplicate_import_are_honest(tmp_path):
    from job_agent.email_research import leads,import_lead
    db,_,p=ready(tmp_path)
    with db.transaction() as c:
        detail={'evidence':{'origin':'received_alert','metadata_only':False,'official_jd_url':'https://example.com/jobs/role-1','source_message_refs':['message-fixture']}}
        c.execute('UPDATE jobs SET discovery_detail=?',(json.dumps(detail),))
        c.execute('INSERT INTO email_message_metadata VALUES(?,?,?,?)',('message-fixture','Ria <ria@example.com>','Frontend opening','2026-10-19T00:00:00Z'))
        c.execute("INSERT INTO m2d_tasks(task_id,kind,job_key,stream,category,payload,status,priority,due_at,attempts,max_attempts,checkpoint,created_at,updated_at) VALUES('fixture','VERIFICATION',?,'GMAIL','EMAIL_OFFICIAL_JD','{}','COMPLETED',1,'now',1,3,'{}','now','now')",(p['job_id'],))
    item=leads(db)['items'][0];assert item['sender']=='Ria <ria@example.com>' and item['verification']=='VERIFIED_OFFICIAL_JD'
    assert 'message-fixture' in item['gmail_url']
    assert import_lead(db,item['id'])==import_lead(db,item['id'])
    with db.transaction() as c:
        assert c.execute('SELECT count(*) FROM jobs').fetchone()[0]==1
        c.execute("UPDATE jobs SET canonical_application_url='https://linkedin.com/jobs/view/123'")
    assert leads(db)['items'][0]['verification']=='RESTRICTED_SOURCE'
    with pytest.raises(ValueError,match='verification_required'):import_lead(db,item['id'])
    with pytest.raises(ValueError,match='not_found'):import_lead(db,'missing')


def test_cached_headers_restore_without_network_or_reparsing_bodies(tmp_path):
    from job_agent.reconciliation_r2 import restore_cached_headers
    import hashlib
    db,_,_=ready(tmp_path);folder=tmp_path/'gmail/message-cache';folder.mkdir(parents=True)
    with db.transaction() as c:c.execute("INSERT INTO gmail_intake VALUES('cached','thread','2026-10-19','[]','VACANCY',1,'fixture',NULL,'now')")
    path=folder/(hashlib.sha256(b'cached').hexdigest()+'.json')
    path.write_text(json.dumps({'id':'cached','payload':{'headers':[{'name':'From','value':'Fixture Recruiter'},{'name':'Subject','value':'Fixture role'}],'body':{'data':'not decoded or accessed'}}}))
    assert restore_cached_headers(db)==1 and restore_cached_headers(db)==0
    with db.transaction() as c:assert tuple(c.execute('SELECT sender,subject FROM email_message_metadata').fetchone())==('Fixture Recruiter','Fixture role')


def test_resolved_personal_answers_transfer_work_to_agent_without_claiming_filled(tmp_path):
    from tests.test_browser_applications import prepared_store
    store,_,key=prepared_store(tmp_path);app=store.batch([key],1)['applications'][0]
    store.update(app['id'],state='NEEDS_USER_ANSWER')
    root=store.db.path.parent/'browser-applications';root.mkdir(exist_ok=True)
    (root/(app['id']+'.json')).write_text(json.dumps({'inventory':[{'id':'country','label':'Country','type':'text','required':True,'visible':True,'value':''}]}))
    JobService(store.db).record_confirmed_application_answers({'country':'India'},'explicit synthetic confirmation')
    reconcile(store.db);row=store.get(app['id'])
    assert row['state']=='NEEDS_EMPLOYER_CHECK' and json.loads(row['missing'])==[]
    assert 'inspect current employer controls' in row['phase']


def test_reconciliation_preserves_explicit_question_approval_and_updates_missing_proposals(tmp_path):
    db,engine,p=ready(tmp_path)
    notice=engine.add_question(p['packet_id'],EmployerQuestion(question='What is your notice period?',source='employer_portal',source_ref='fixture:notice',field_kind='NOTICE'))
    consent=engine.add_question(p['packet_id'],EmployerQuestion(question='I agree to the notice period terms',source='employer_portal',source_ref='fixture:consent',field_kind='NOTICE'))
    q=next(q for q in engine.get(p['packet_id'])['questions'] if q['question_id']==consent)
    assert q['answer'] is None
    engine.answer_question(notice,'My manually approved notice','USER')
    JobService(db).record_confirmed_application_answers({'notice_period':'60 days'},'explicit synthetic update')
    reconcile(db)
    q=next(q for q in engine.get(p['packet_id'])['questions'] if q['question_id']==notice)
    assert q['answer']=='My manually approved notice'


def test_residence_and_specific_employer_disclosures_do_not_imply_other_answers():
    from job_agent.application_answers import answer
    facts={'country':'India','employment_restrictions':'No'}
    for label in ['Country of citizenship','Country of birth','Passport country']:
        assert answer({'label':label,'type':'text'},facts,{},'','Engineer','Example',True)==(None,None)
    assert answer({'label':'Employment restrictions','type':'text'},facts,{},'','Engineer','Other',True)==(None,None)


def test_named_missing_packet_answers_resolve_from_current_confirmation(tmp_path):
    db,engine,p=ready(tmp_path)
    with db.transaction() as c:
        c.execute("UPDATE jobs SET company='GitLab'")
        c.execute('UPDATE application_packets SET missing_information=?',(json.dumps(['previous GitLab employment or consulting','employment/post-employment restrictions','headcount']),))
    JobService(db).record_confirmed_application_answers({'gitlab_previous_work':'No','employment_restrictions':'No'},'explicit GitLab-only synthetic confirmation')
    # Manual text is retained while metadata questions are independently reconciled.
    v=p['version_data'];engine.edit(p['packet_id'],PacketEdit(subject=v['subject'],email_text=v['email_text'],email_html=v['email_html'],supporting_statement=v['supporting_statement']))
    reconcile(db)
    assert engine.get(p['packet_id'])['missing_information']==['headcount']


def test_missing_current_vacancy_identity_retains_prior_text_and_records_blocker(tmp_path):
    db,engine,p=ready(tmp_path);old=engine.get(p['packet_id'])
    with db.transaction() as c:c.execute('UPDATE jobs SET title=NULL,company=NULL')
    result=reconcile(db);current=engine.get(p['packet_id'])
    assert result['identity_blockers'] and 'vacancy_identity_unverified' in current['missing_information']
    assert current['version_data']['email_text']==old['version_data']['email_text']
    assert current['version_data']['provenance']['fact_reconciliation']['prior_text_retained'] is True
    assert reconcile(db)['revised_packets']==0


def test_metadata_reconciliation_preserves_existing_worker_phase(tmp_path):
    from tests.test_browser_applications import prepared_store
    store,_,key=prepared_store(tmp_path);app=store.batch([key],1)['applications'][0]
    store.update(app['id'],inspection={'stage':'Old inspected stage'})
    store.update(app['id'],phase='Current durable worker phase')
    reconcile(store.db)
    assert store.get(app['id'])['phase']=='Current durable worker phase'

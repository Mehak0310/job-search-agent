import json
import socket
from types import SimpleNamespace

import pytest
from playwright.sync_api import sync_playwright

from job_agent.browser_store import BrowserStore,vacancy_identity
from job_agent.browser_forms import Dispatcher,NetworkBoundary,GUARD_JS,inventory,public_url
from job_agent.application_answers import answer,tailored
from job_agent import browser_applications as runner
from tests.test_m3 import setup_engine

URL='https://job-boards.greenhouse.io/example/jobs/12345'

def test_confirmed_restrictions_and_employer_scoped_history():
    facts={'employment_restrictions':'No','gitlab_previous_work':'No'}
    field={'label':'Are you subject to any employment agreements and/or post-employment restrictions with your current employer or a past employer?*','type':'text'}
    assert answer(field,facts,{},'','Engineer','GitLab')[0]=='No'
    field['label']='Have you previously worked at or consulted for GitLab?'
    assert answer(field,facts,{},'','Engineer','GitLab')[0]=='No'
    field['label']='Have you previously worked at MongoDB?'
    assert answer(field,facts,{},'','Engineer','MongoDB')==(None,None)

def test_confirmed_answer_revision_preserves_profile(tmp_path):
    from job_agent.database import Database
    from job_agent.service import JobService
    service=JobService(Database(tmp_path/'jobs.sqlite3'))
    before=service.get_candidate_profile()
    result=service.record_confirmed_application_answers({'gitlab_previous_work':'No'},'explicit fixture user decision')
    after=service.get_candidate_profile()
    assert result['version']==before['version']+1
    assert after['approved_application_answers']['gitlab_previous_work']=='No'
    assert after['professional_skills']==before['professional_skills']
    with service.db.transaction() as conn:
        assert conn.execute('SELECT count(*) FROM candidate_profile_revisions').fetchone()[0]==1

HTML='''<h1>Senior Frontend Engineer</h1><p>Responsibilities: build frontend components, API integration and testing.</p>
<form id="application" action="https://job-boards.greenhouse.io/example/apply" method="post">
<label>Full name*<input id="name" required></label><label>Email*<input id="email" type="email" required></label>
<label>Current country*<select id="residence" required><option value="">Choose</option><option value="IN">India</option><option value="US">United States</option></select></label>
<label>Why are you interested in this role?<textarea id="motivation" maxlength="5000"></textarea></label>
<label>Resume*<input id="resume" type="file" required></label><span id="filename"></span>
<label>Legal attestation*<input id="consent" type="checkbox" required></label>
<button id="misleading">Continue</button></form>
<script>window.submits=0;document.querySelector('form').addEventListener('submit',()=>window.submits++);
resume.onchange=async()=>{await fetch('https://grnhse-prod-jben-us-west-2.s3.us-west-2.amazonaws.com/',{method:'POST',body:new FormData()});filename.textContent=resume.files[0].name;};</script>'''


@pytest.fixture(scope='module')
def browser():
    with sync_playwright() as p:
        b=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
        yield b
        b.close()


@pytest.fixture
def frame(browser):
    context=browser.new_context();page=context.new_page();page.set_content(HTML)
    yield page
    context.close()


def global_dns(*args,**kwargs):return [(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',443))]


def prepared_store(tmp_path):
    db,engine,key=setup_engine(tmp_path)
    with db.transaction() as conn:
        conn.execute('UPDATE jobs SET application_url=?,canonical_application_url=? WHERE id=?',(URL,URL,key))
    approve_requirements(db,key)
    engine.prepare(key)
    return BrowserStore(db),engine,key


def approve_requirements(db,key):
    """Explicit synthetic accepted source/evidence; never used against the live database."""
    import hashlib
    with db.transaction() as conn:
        profile=json.loads(conn.execute('SELECT config FROM candidate_profiles_v2').fetchone()[0]);profile['professional_skills']=sorted(set(profile.get('professional_skills',[]))|{'react'});profile.setdefault('skill_evidence',{})['react']=[{'source':'user_confirmation','reference':'explicit isolated fixture evidence'}]
        conn.execute('UPDATE candidate_profiles_v2 SET config=?',(json.dumps(profile),))
        url=conn.execute('SELECT application_url FROM jobs WHERE id=?',(key,)).fetchone()[0];description='React required.'
        conn.execute('UPDATE jobs SET description=?,required_skills=?,required_experience_min=NULL,required_experience_max=NULL,discovery_detail=? WHERE id=?',(description,json.dumps(['react']),json.dumps({'requirements_source':{'content_status':'FULL','source_url':url,'description_sha256':hashlib.sha256(description.encode()).hexdigest(),'retrieval_version':'explicit-isolated-priority-fixture'}}),key))
        conn.execute("UPDATE job_operational_state SET active_state='PASS',india_state='PASS',headcount_state='PASS',payroll_state='PASS' WHERE job_id=?",(key,))


def test_inventory_scoping_limits_and_unknown_required(frame):
    fields=inventory(frame);by_id={f['id']:f for f in fields}
    assert by_id['name']['label']=='Full name*' and by_id['name']['required']
    assert by_id['motivation']['max_length']==5000
    assert by_id['residence']['options'][1]['label']=='India'
    assert answer(by_id['consent'],{}, {},'','Role','Employer')==(None,None)
    assert answer(dict(by_id['name'],label='Last name'),{'full_name':'Single'}, {},'','Role','Employer')==(None,None)
    dispatch=Dispatcher(frame);dispatch.act('FILL',by_id['name'],'Synthetic')
    assert frame.locator('#name').input_value()=='Synthetic'
    dispatch.act('SELECT',by_id['residence'],'India')
    assert frame.locator('#residence option:checked').inner_text()=='India'
    with pytest.raises(ValueError,match='membership'):dispatch.act('SELECT',by_id['residence'],'Canada')
    with pytest.raises(ValueError,match='character_limit'):dispatch.act('FILL',dict(by_id['motivation'],max_length=3),'too long')


def test_dispatch_dom_and_implicit_enter_cannot_submit(frame):
    frame.evaluate(GUARD_JS)
    dispatch=Dispatcher(frame)
    with pytest.raises(ValueError,match='final_or_ambiguous'):dispatch.act('NAVIGATE',locator=frame.locator('#misleading'))
    with pytest.raises(ValueError,match='final_or_ambiguous'):dispatch.act('ENTER')
    frame.locator('#name').fill('Synthetic');frame.locator('#email').fill('test@example.com')
    frame.locator('#misleading').click();frame.locator('#name').press('Enter')
    frame.evaluate("document.getElementById('application').requestSubmit()")
    frame.evaluate("document.getElementById('application').submit()")
    assert frame.evaluate('window.submits')==0


def test_ambiguous_locators_never_choose_first_input(frame):
    frame.set_content('<label>Duplicate<input name="same"></label><label>Duplicate<input name="same"></label>')
    with pytest.raises(ValueError,match='ambiguous'):Dispatcher(frame).act('FILL',inventory(frame)[0],'not allowed')


def test_conditional_questions_and_supported_frame(browser):
    context=browser.new_context();page=context.new_page()
    page.set_content('''<label>Country<select id="c" onchange="document.getElementById('extra').hidden=false"><option>Choose</option><option>India</option></select></label><div id="extra" hidden><label>Required tax ID<input id="tax" required></label></div>''')
    assert not next(f for f in inventory(page) if f['id']=='tax')['visible']
    Dispatcher(page).act('SELECT',next(f for f in inventory(page) if f['id']=='c'),'India')
    assert next(f for f in inventory(page) if f['id']=='tax')['visible']
    page.set_content('<iframe srcdoc="&lt;label&gt;Email&lt;input id=email&gt;&lt;/label&gt;"></iframe>')
    assert inventory(page.frames[1])[0]['label']=='Email'
    context.close()


def test_custom_dropdown_exact_membership_and_radio_readback(frame):
    frame.set_content('''<label>Residence<input id="custom" role="combobox" oninput="document.getElementById('opts').hidden=false"></label>
      <div class="singleValue"></div><div id="opts" hidden><div role="option" onclick="document.querySelector('.singleValue').textContent='Canada';custom.value='';opts.hidden=true">Canada</div><div role="option" onclick="document.querySelector('.singleValue').textContent='India';custom.value='';opts.hidden=true">India</div></div>
      <fieldset><legend>Authorized to work in India?</legend><label>Yes<input type="radio" name="work" value="y" required></label><label>No<input type="radio" name="work" value="n" required></label></fieldset>''')
    fields=inventory(frame);dispatch=Dispatcher(frame)
    assert dispatch.act('SELECT',fields[0],'India')=='India'
    radio=next(f for f in fields if f['type']=='radio' and f['label']=='Yes')
    assert radio['group']=='Authorized to work in India?'
    assert dispatch.act('SELECT',radio,'Yes')=='Yes'
    assert frame.locator('input[value=y]').is_checked() and not frame.locator('input[value=n]').is_checked()


def test_detached_file_input_after_success_is_supported(frame):
    frame.set_content('''<label>Resume<input id="resume" type="file" onchange="this.remove()"></label>''')
    result=Dispatcher(frame).act('UPLOAD',inventory(frame)[0],{'name':'synthetic.pdf','mimeType':'application/pdf','buffer':b'synthetic'})
    assert result==['synthetic.pdf']
    assert frame.locator('#resume').count()==0


def test_readonly_yes_no_combobox_is_selected_without_typing(frame):
    frame.set_content('''<label>Sponsorship<input id="s" role="combobox" readonly onclick="opts.hidden=false"></label><div class="singleValue"></div><div id="opts" hidden><div role="option" onclick="document.querySelector('.singleValue').textContent='No';opts.hidden=true">No</div><div role="option">Yes</div></div>''')
    assert Dispatcher(frame).act('SELECT',inventory(frame)[0],'No')=='No'


def test_adjacent_custom_selects_do_not_share_readback(frame):
    frame.set_content('''<div class="select__control"><span class="select__single-value">India</span><label>Country<input id="c" role="combobox"></label></div><div class="select__control"><span class="select__single-value">No</span><label>Sponsorship<input id="s" role="combobox"></label></div><div class="select__control"><label>Unanswered<input id="u" role="combobox" value="search text only"></label></div>''')
    values={f['id']:f['value'] for f in inventory(frame)}
    assert values=={'c':'India','s':'No','u':''}


def test_persisted_navigation_retry_exhaustion_has_one_owner(tmp_path,monkeypatch):
    from playwright.sync_api import TimeoutError
    store,engine,key=prepared_store(tmp_path);app=store.batch([key],1)['applications'][0]
    calls=[];monkeypatch.setattr(runner.time,'sleep',lambda delay:None)
    def fail():calls.append(1);raise TimeoutError('synthetic')
    with pytest.raises(TimeoutError):runner.run_read(store,app['id'],'navigate','fixed',fail)
    assert len(calls)==3
    with pytest.raises(ValueError,match='budget'):runner.run_read(BrowserStore(store.db),app['id'],'navigate','fixed',fail)
    assert len(calls)==3


def test_api_batch_switch_report_and_origin_gate(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from job_agent.main import create_app
    store,engine,key=prepared_store(tmp_path);launched=[]
    monkeypatch.setattr(runner,'launch_worker',lambda db,batch:launched.append(batch) or 100)
    monkeypatch.setattr(runner,'switch_tab',lambda db,identifier:{'state':'SESSION_LOST'})
    monkeypatch.setattr(runner,'connect_login',lambda db,portal:{'portal':portal,'state':'USER_LOGIN_REQUIRED'})
    app=create_app(store.db.path)
    with TestClient(app) as client:
        assert client.post('/api/browser/batches',json={'limit':6}).status_code==422
        assert client.post('/api/browser/batches',json={'limit':1},headers={'origin':'https://evil.test'}).status_code==403
        result=client.post('/api/browser/batches',json={'job_ids':[key],'limit':1}).json();assert result['selected']==1 and launched
        identifier=result['applications'][0]['id']
        assert client.post('/api/browser/applications/'+identifier+'/switch').json()['state']=='SESSION_LOST'
        assert client.post('/api/browser/connect/linkedin').json()['state']=='USER_LOGIN_REQUIRED'
        from playwright.sync_api import TimeoutError as BrowserTimeout
        def timeout_login(db,portal):raise BrowserTimeout('private browser diagnostic')
        monkeypatch.setattr(runner,'connect_login',timeout_login)
        failure=client.post('/api/browser/connect/naukri')
        assert failure.status_code==409
        assert 'Check the dedicated Chrome window' in failure.json()['detail']
        assert 'private browser diagnostic' not in failure.text
        assert client.post('/api/browser/applications/'+identifier+'/reported-submitted').json()['submission_verified'] is False
        assert client.get('/api/browser/applications').json()==[]
        assert client.get('/api/browser/applications?include_history=true').json()[0]['state']=='USER_REPORTED_SUBMITTED'


@pytest.mark.parametrize('url',['http://example.com','https://user:pw@example.com','https://127.0.0.1','file:///x','https://example.com:8443'])
def test_unsafe_urls(url):
    with pytest.raises(ValueError):public_url(url,lambda *a,**k:[(2,1,6,'',('127.0.0.1',443))])


def test_network_final_post_blocked_and_upload_scope_is_narrow():
    boundary=NetworkBoundary('job-boards.greenhouse.io',dns=global_dns)
    class Route:
        def __init__(self,url,method):self.request=SimpleNamespace(url=url,method=method,is_navigation_request=lambda:False);self.outcome=None
        def fallback(self):self.outcome='allowed'
        def abort(self):self.outcome='blocked'
    route=Route('https://job-boards.greenhouse.io/example/apply','POST');boundary.route(route);assert route.outcome=='blocked'
    boundary.upload=True
    route=Route('https://grnhse-prod-jben-us-west-2.s3.us-west-2.amazonaws.com/','POST');boundary.route(route);assert route.outcome=='allowed'
    route=Route('https://job-boards.greenhouse.io/example/apply','POST');boundary.route(route);assert route.outcome=='blocked'
    route=Route('https://evil.test/','PUT');boundary.route(route);assert route.outcome=='blocked'


def test_duplicate_history_states_and_persisted_attempt_budget(tmp_path):
    store,engine,key=prepared_store(tmp_path)
    batch=store.batch([key],1);app=batch['applications'][0]
    assert store.batch([key],1)['selected']==0
    with pytest.raises(ValueError):store.batch([key]*6,6)
    for _ in range(3):
        identifier,perform=store.begin_operation(app['id'],'navigate','same');assert perform
        store.end_operation(identifier,'FAILED','TimeoutError')
    restarted=BrowserStore(store.db)
    with pytest.raises(ValueError,match='budget'):restarted.begin_operation(app['id'],'navigate','same')
    identifier,_=store.begin_operation(app['id'],'upload','bytes',write=True)
    with pytest.raises(ValueError,match='uncertain'):restarted.begin_operation(app['id'],'upload','bytes',write=True)
    store.end_operation(identifier,'UNCERTAIN')
    with pytest.raises(ValueError,match='uncertain'):restarted.begin_operation(app['id'],'upload','bytes',write=True)
    store.update(app['id'],state='SESSION_LOST')
    assert store.batch([key],1,reconstruct=True)['selected']==1
    store.update(app['id'],state='USER_REPORTED_SUBMITTED')
    with pytest.raises(ValueError,match='submission_history'):store.job(key)
    assert vacancy_identity({'company':'Example Corp','application_url':URL})==vacancy_identity({'company':'Example Corp','application_url':URL+'?utm_source=email'})


def test_known_office_and_remote_country_incompatibilities_block_backend(tmp_path):
    store,engine,key=prepared_store(tmp_path)
    with store.db.transaction() as conn:
        conn.execute("UPDATE candidate_profiles_v2 SET config=json_set(config,'$.preferred_locations',json('[\"Noida\",\"remote india\"]')) WHERE id=1")
        conn.execute("UPDATE jobs SET location='Pune',work_mode='hybrid' WHERE id=?",(key,))
    with pytest.raises(ValueError,match='office_location'):store.job(key)
    with store.db.transaction() as conn:conn.execute("UPDATE jobs SET location='Remote, US',work_mode='remote' WHERE id=?",(key,))
    with pytest.raises(ValueError,match='country_scope'):store.job(key)


def test_grounded_role_answers_use_full_jd_and_scope_cloud():
    profile={'professional_skills':['angular','react','typescript','python','fastapi','rag','faiss','azure fundamentals'],
             'professional_ai_summary':['Document Intelligence: grounded RAG, FAISS retrieval and tests.']}
    frontend,fp=tailored(profile,'Own reusable frontend components and UI architecture.','Angular Engineer','Example')
    ai,ap=tailored(profile,'Build agentic AI and RAG integrations with APIs and Azure.','AI Engineer','Example')
    assert frontend!=ai and 'Document Intelligence' in ai and 'fundamentals level' in ai
    assert fp['jd_sha256']!=ap['jd_sha256'] and 'Java' not in frontend
    value,_=answer({'label':'Why this role?','type':'textarea','max_length':10},{},profile,'Build RAG','AI','Example')
    assert value is None


def test_sponsorship_question_is_not_mistaken_for_contact_location():
    field={'label':'Will you now or in the future require sponsorship for a visa to remain in your current location?*','type':'text','max_length':-1}
    facts={'city':'Synthetic City','country':'India','india_sponsorship':'No'}
    assert answer(field,facts,{},'India role','Role','Example',india=True)==('No','india_sponsorship')
    assert answer({**field,'label':'Which location are you applying for?'},facts,{},'','Role','Example')==(None,None)


def test_end_to_end_fixture_fill_upload_readback_and_manual_handoff(tmp_path,browser,monkeypatch):
    store,engine,key=prepared_store(tmp_path);batch=store.batch([key],1);app=store.get(batch['applications'][0]['id'])
    root=runner.root_for(store.db);root.mkdir(parents=True)
    resume=tmp_path/'resume.pdf';resume.write_bytes(b'synthetic fixture bytes')
    from job_agent.document_manifest import sha256
    manifest={'documents':[{'canonical_name':'Resume.pdf','local_path':str(resume),'sha256':sha256(resume)}]}
    profile={'professional_skills':['react','typescript','testing'],'version':1}
    monkeypatch.setattr(runner,'approved_facts',lambda db:(profile,{'full_name':'Synthetic','email':'test@example.com','country':'India'},{},manifest))
    monkeypatch.setattr(runner,'public_url',lambda url:url)
    monkeypatch.setattr(runner,'NetworkBoundary',lambda host:NetworkBoundary(host,dns=global_dns))
    context=browser.new_context()
    requests=[]
    def respond(route):
        requests.append((route.request.method,route.request.url))
        if 'amazonaws.com' in route.request.url:return route.fulfill(status=204,headers={'access-control-allow-origin':'*'})
        route.fulfill(status=200,content_type='text/html',body=HTML)
    context.route('**/*',respond)
    runner.prepare_one(store,app,browser,{'webSocketDebuggerUrl':'ws://127.0.0.1/devtools/browser/fixture'})
    result=store.get(app['id']);docs=json.loads(result['documents'])
    assert result['state']=='NEEDS_USER_ANSWER' # consent deliberately unanswered
    assert docs[0]['verified'] and docs[0]['filename_visible']
    page=runner.find_page(browser,result['target_id']);assert page is not None and not page.is_closed()
    assert page.locator('#name').input_value()=='Synthetic'
    assert page.evaluate('window.__jobPreparationActive') is False
    assert not any(method=='POST' and url.endswith('/apply') for method,url in requests)
    # Dashboard serialization does not leak copied private field values.
    assert 'test@example.com' not in json.dumps(store.list())
    context.close()


def test_review_queue_submission_and_unavailable_persist(tmp_path):
    from fastapi.testclient import TestClient
    from job_agent.main import create_app
    from job_agent.review_queue import hidden_job_ids
    store,engine,key=prepared_store(tmp_path)
    assert engine.list()
    batch=store.batch([key],1);identifier=batch['applications'][0]['id']
    store.update(identifier,state='USER_REPORTED_SUBMITTED')
    assert engine.list()==[]
    assert store.list()==[]
    assert store.list(include_history=True)[0]['state']=='USER_REPORTED_SUBMITTED'
    assert key in hidden_job_ids(store.db)
    assert store.batch([key],1)['selected']==0
    # Preserve history: user reporting never becomes confirmation evidence.
    assert store.get(identifier)['confirmation_ref'] is None


def test_unavailable_removal_survives_reload_without_deleting_job(tmp_path):
    from fastapi.testclient import TestClient
    from job_agent.main import create_app
    store,engine,key=prepared_store(tmp_path)
    before=engine.list()[0]['current_version']
    with TestClient(create_app(store.db.path)) as client:
        assert client.post('/api/jobs/'+key+'/review-dismissal').json()['history_preserved']
        assert client.post('/api/jobs/'+key+'/review-dismissal').status_code==200
        assert client.get('/api/jobs/'+key).status_code==200
        assert client.get('/api/m3/packets').json()==[]
    assert engine.list()==[]
    assert store.batch([key],1)['selected']==0
    with store.db.transaction() as conn:
        assert conn.execute('SELECT current_version FROM application_packets').fetchone()[0]==before
        assert conn.execute("SELECT count(*) FROM job_evidence WHERE kind='review_queue_dismissal'").fetchone()[0]==1


def test_missing_and_closed_links_do_not_enter_review(tmp_path):
    store,engine,key=prepared_store(tmp_path)
    with store.db.transaction() as conn:conn.execute("UPDATE jobs SET application_url='',canonical_application_url=NULL WHERE id=?",(key,))
    assert engine.list()==[]
    assert store.batch([key],1)['selected']==0


def test_unknown_employer_identity_is_safe():
    assert vacancy_identity({'company':None,'application_url':'https://example.com/jobs/123'})


def test_submission_history_suppresses_later_statuses(tmp_path):
    from job_agent.service import JobService
    from job_agent.models import Status
    store,engine,key=prepared_store(tmp_path)
    service=JobService(store.db)
    service.set_status(key,Status.SUBMITTED)
    service.set_status(key,Status.INTERVIEW)
    assert engine.list()==[]
    assert store.batch([key],1)['selected']==0
    service.set_status(key,Status.NEW)
    assert engine.list()==[]


@pytest.mark.parametrize('url',['',None,'javascript:alert(1)','https://','https://user:secret@example.com/job'])
def test_unusable_application_url_is_not_reviewable(url):
    from job_agent.review_queue import usable_url
    assert not usable_url(url)

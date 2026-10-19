import json
from pathlib import Path
import pytest
from job_agent.database import Database
from job_agent.application_answers import answer,question_key
from job_agent.service import JobService
from job_agent.review_workflow import pending_questions,save_answers,progress
from tests.test_browser_applications import prepared_store,frame,browser


def field(label,kind='text',**extra):return {'label':label,'type':kind,**extra}


def test_saved_common_facts_and_formatting():
 facts={'full_name':'Jordan Fixture','surname_fallbacks':json.dumps(['.','_','Jordan Fixture']),'phone':'+91 9876543210','phone_format':'national','current_company':'Example','current_title':'Senior Consultant','country':'India','expected_compensation':'42 LPA','notice_period':'45 days'}
 for label,expected in [('Last Name*','.'),('Phone','9876543210'),('Most Recent Employer*','Example'),('Most Recent Job Title*','Senior Consultant'),('What is your current country of residence?*','India'),('Salary Expectation*','42 LPA'),('What is your Current Location?','Noida')]:
  result,_=answer(field(label),{**facts,'city':'Noida'},{},'','Engineer','Example',True);assert result==expected
 assert answer(field('International phone (include country code)'),facts,{},'','Engineer','Example',True)[0]==facts['phone']
 assert answer(field('I agree to the privacy policy','checkbox'),facts,{},'','Engineer','Example',True)==(None,None)


def test_question_scope_does_not_transfer_employer_declarations():
 key=question_key('Have you worked here before?','Example')
 facts={key:'No'}
 assert answer(field('Have you worked here before?'),facts,{},'','Engineer','Example')[0]=='No'
 assert answer(field('Have you worked here before?'),facts,{},'','Engineer','Other')==(None,None)


def test_portal_answer_persists_and_known_answers_are_not_prompted(tmp_path):
 store,engine,key=prepared_store(tmp_path);app=store.batch([key],1)['applications'][0]
 service=JobService(store.db);service.record_confirmed_application_answers({'country':'India'},'explicit fixture fact')
 folder=store.db.path.parent/'browser-applications';folder.mkdir(exist_ok=True)
 fields=[{'id':'country','name':'country','label':'Country','type':'text','required':True,'visible':True,'value':''},{'id':'unknown','name':'unknown','label':'Years in B2B SaaS','type':'text','required':True,'visible':True,'value':''}]
 (folder/(app['id']+'.json')).write_text(json.dumps({'inventory':fields,'full_jd':'Actual role'}))
 questions=pending_questions(store.db,app['id']);assert len(questions)==1 and questions[0]['label']=='Years in B2B SaaS'
 saved=save_answers(store.db,app['id'],[{'key':questions[0]['key'],'value':'2','reuse':True}]);assert saved['version']>1
 assert pending_questions(store.db,app['id'])==[]
 assert JobService(Database(store.db.path)).get_candidate_profile()['approved_application_answers'][question_key('Years in B2B SaaS','','shared')]=='2'
 with pytest.raises(ValueError):save_answers(store.db,app['id'],[{'key':'invented','value':'Yes'}])


def test_progress_never_calls_blocked_forms_ready(tmp_path):
 store,engine,key=prepared_store(tmp_path);batch=store.batch([key],1);app=batch['applications'][0]
 store.update(app['id'],state='NEEDS_USER_ANSWER')
 current=progress(store.db)['batches'][0]
 assert current['processed']==1 and current['ready']==0 and current['needs_answers']==1


def test_surname_fallback_only_after_visible_rejection(frame):
 from job_agent.browser_applications import surname_fill
 from job_agent.browser_forms import Dispatcher,inventory
 frame.set_content('<label>Last Name<input id="surname" oninput="this.setAttribute(\'aria-invalid\',String(this.value===\'.\')))"></label>')
 # Native pattern provides independent visible client-side rejection.
 frame.locator('#surname').evaluate("e=>{e.pattern='[_A-Za-z]+';e.removeAttribute('oninput');}")
 result=surname_fill(Dispatcher(frame),inventory(frame)[0],'.',{'surname_fallbacks':json.dumps(['.','_','Jordan Fixture'])})
 assert result=='_' and frame.locator('#surname').input_value()=='_'


def test_worker_failure_finishes_batch_without_claiming_ready(tmp_path,monkeypatch):
    from job_agent import browser_applications as runner
    store,engine,key=prepared_store(tmp_path);batch=store.batch([key],1)
    def busy(*args):raise ValueError('workflow_already_running')
    monkeypatch.setattr(runner,'execute_batch',busy)
    assert runner.run_worker_batch(store.db,batch['batch_id'])['state']=='ERROR'
    current=progress(store.db)['batches'][0]
    assert current['status']=='ERROR' and current['ready']==0 and current['agent_checks']==1


def test_recovery_never_refills_a_different_job_in_the_old_tab(monkeypatch):
    from job_agent import browser_applications as runner
    from types import SimpleNamespace
    wrong=SimpleNamespace(url='https://job-boards.greenhouse.io/example/jobs/999')
    correct=SimpleNamespace(url='https://job-boards.greenhouse.io/example/jobs/123')
    monkeypatch.setattr(runner,'find_page',lambda *args:wrong)
    browser=SimpleNamespace(contexts=[SimpleNamespace(pages=[wrong,correct])])
    assert runner.recover_page(browser,{'target_id':'old','url':correct.url}) is correct
    browser.contexts[0].pages=[wrong]
    assert runner.recover_page(browser,{'target_id':'old','url':correct.url}) is None


def test_answer_api_validates_inventory_and_persists_before_sync(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from job_agent.main import create_app
    from job_agent import browser_applications as runner
    store,engine,key=prepared_store(tmp_path);application=store.batch([key],1)['applications'][0]
    folder=store.db.path.parent/'browser-applications';folder.mkdir(exist_ok=True)
    (folder/(application['id']+'.json')).write_text(json.dumps({'inventory':[{'id':'experience','name':'experience','label':'Years in B2B SaaS','type':'text','required':True,'visible':True,'value':'','max_length':2}]}))
    called=[];monkeypatch.setattr(runner,'launch_sync_worker',lambda db,identifier=None:called.append(identifier) or 123)
    with TestClient(create_app(store.db.path)) as client:
        questions=client.get('/api/browser/applications/'+application['id']+'/questions').json()
        assert len(questions)==1
        response=client.post('/api/browser/applications/'+application['id']+'/answers',json={'answers':[{'key':questions[0]['key'],'value':'2','reuse':True}]})
        assert response.status_code==200 and called==[application['id']]
        assert client.get('/api/browser/applications/'+application['id']+'/questions').json()==[]
        assert client.get('/api/browser/saved-facts').status_code==200

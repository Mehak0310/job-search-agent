from contextlib import contextmanager
from job_agent import browser_applications as runner
from job_agent.orchestration import login_tick
from tests.test_browser_applications import browser,frame,prepared_store


def test_supported_form_access_is_required_for_login_resume(frame,monkeypatch):
    monkeypatch.setattr(runner,'recover_page',lambda browser,item:frame)
    monkeypatch.setattr(runner,'ats_for',lambda url:'greenhouse')
    frame.set_content('<label>Password<input type="password"></label>')
    assert runner.probe_employer_login(None,{})=='WAITING'
    frame.set_content('<p>Verify you are human</p>')
    assert runner.probe_employer_login(None,{})=='HUMAN_ONLY'
    frame.set_content('<label>Full name<input></label><label>Email<input type="email"></label>')
    assert runner.probe_employer_login(None,{})=='VERIFIED'
    monkeypatch.setattr(runner,'ats_for',lambda url:None)
    assert runner.probe_employer_login(None,{})=='WAITING'
    monkeypatch.setattr(runner,'recover_page',lambda browser,item:None)
    assert runner.probe_employer_login(None,{})=='LOST'


def test_positive_login_resumes_only_after_eligibility_recheck(tmp_path,monkeypatch):
    store,_,key=prepared_store(tmp_path);batch=store.batch([key],1);app=batch['applications'][0]
    store.update(app['id'],state='NEEDS_LOGIN',inspection={'error_code':'authentication_required'})
    calls=[]
    @contextmanager
    def connection():yield object()
    class Workers:
        def assert_owner(self,*args):pass
        def checkpoint(self,*args):pass
    monkeypatch.setattr(runner,'browser_connection',connection)
    monkeypatch.setattr(runner,'probe_employer_login',lambda browser,item:'VERIFIED')
    monkeypatch.setattr(runner.time,'sleep',lambda seconds:None)
    def prepare(store,item,browser,metadata,upload):
        calls.append((item['id'],upload));store.update(item['id'],state='READY_FOR_USER_REVIEW')
    monkeypatch.setattr(runner,'prepare_one',prepare)
    runner.wait_for_employer_logins(store.db,batch['batch_id'],Workers(),'workflow','owner',{},False)
    assert calls==[(app['id'],False)]
    assert login_tick(store.db,app['id'])=='VERIFIED'


def test_login_resume_blocked_by_changed_eligibility(tmp_path,monkeypatch):
    store,_,key=prepared_store(tmp_path);batch=store.batch([key],1);app=batch['applications'][0]
    store.update(app['id'],state='NEEDS_LOGIN',inspection={'error_code':'authentication_required'})
    with store.db.transaction() as c:c.execute("UPDATE job_operational_state SET india_state='FAIL'")
    @contextmanager
    def connection():yield object()
    class Workers:
        def assert_owner(self,*args):pass
        def checkpoint(self,*args):pass
    monkeypatch.setattr(runner,'browser_connection',connection)
    monkeypatch.setattr(runner,'probe_employer_login',lambda browser,item:'VERIFIED')
    monkeypatch.setattr(runner.time,'sleep',lambda seconds:None)
    monkeypatch.setattr(runner,'prepare_one',lambda *args:(_ for _ in ()).throw(AssertionError('must not fill')))
    runner.wait_for_employer_logins(store.db,batch['batch_id'],Workers(),'workflow','owner',{},False)
    with store.db.transaction() as c:assert c.execute('SELECT state FROM employer_login_waits').fetchone()[0]=='ERROR'

import pytest
from job_agent import orchestration as o
from tests.test_browser_applications import prepared_store


@pytest.mark.parametrize('state',['USER_REPORTED_SUBMITTED','SESSION_LOST','ERROR'])
def test_ready_alert_resolves_without_losing_history(tmp_path,state):
    store,_,key=prepared_store(tmp_path);app=store.batch([key],1)['applications'][0]
    store.update(app['id'],state='READY_FOR_USER_REVIEW')
    before=o.notifications(store.db)['items'][0]
    assert before['attention']
    store.update(app['id'],state=state)
    after=o.notifications(store.db)['items'][0]
    assert after['id']==before['id'] and after['resolved'] and not after['attention'] and not after['audible']
    revision=after['revision'];o.record_progress(store.db,app['id'])
    assert o.notifications(store.db)['items'][0]['revision']==revision


def test_login_and_question_alerts_resolve_and_new_ready_can_alert(tmp_path):
    store,_,key=prepared_store(tmp_path);app=store.batch([key],1)['applications'][0]
    store.update(app['id'],state='NEEDS_LOGIN',inspection={'error_code':'captcha'})
    o.publish(store.db,app['batch_id']+':questions',app['batch_id'],'MISSING_INFORMATION',{'count':1})
    store.update(app['id'],state='READY_FOR_USER_REVIEW')
    rows={r['kind']:r for r in o.notifications(store.db)['items']}
    assert rows['LOGIN_REQUIRED']['resolved'] and rows['MISSING_INFORMATION']['resolved']
    original=rows['READY'];store.update(app['id'],state='ERROR');store.update(app['id'],state='READY_FOR_USER_REVIEW')
    current=next(r for r in o.notifications(store.db)['items'] if r['kind']=='READY')
    assert current['id']==original['id'] and current['attention'] and not current['resolved']


def test_replaced_ready_form_is_a_new_condition_even_at_same_count(tmp_path):
    from tests.test_priority_queue import jobs
    from job_agent.browser_store import BrowserStore
    db,_,_=jobs(tmp_path,scores=(95,90));store=BrowserStore(db);batch=store.batch(limit=2)
    first,second=batch['applications'];store.update(first['id'],state='READY_FOR_USER_REVIEW')
    old=next(r for r in o.notifications(db)['items'] if r['kind']=='READY');o.acknowledge(db,old['id'],old['revision'])
    with db.transaction() as c:
        c.execute("UPDATE browser_applications SET state='ERROR' WHERE id=?",(first['id'],))
        c.execute("UPDATE browser_applications SET state='READY_FOR_USER_REVIEW' WHERE id=?",(second['id'],))
    o.record_progress(db,second['id'])
    current=next(r for r in o.notifications(db)['items'] if r['kind']=='READY')
    assert current['attention'] and current['payload']['ready']==1
    assert current['payload']['application_ids']==[second['id']]

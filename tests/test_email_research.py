import json
import httpx
import pytest
from job_agent.email_research import proper_title,read_official,start,execute,leads
from tests.test_browser_applications import prepared_store


def test_generic_alert_is_not_a_job_title():
 for title in ['Open job -alert','View job','Apply now','https://example.com/job']:assert proper_title(title) is None
 assert proper_title('Senior Angular Engineer')=='Senior Angular Engineer'
 assert proper_title('Application to Example successfully submitted') is None
 assert proper_title('Applied AI Engineer II')=='Applied AI Engineer II'


def test_email_view_has_real_titles_and_receipts_are_not_researched(tmp_path):
 store,engine,key=prepared_store(tmp_path)
 with store.db.transaction() as c:
  c.execute("UPDATE jobs SET title='Senior Angular Engineer',discovery_detail=?,application_url='https://careers.example.com/jobs/123',canonical_application_url=NULL WHERE id=?",(json.dumps({'evidence':{'origin':'received_alert','metadata_only':True}}),key))
 result=leads(store.db)
 assert result['named']==1 and result['items'][0]['title']=='Senior Angular Engineer'
 assert result['items'][0]['research_state']=='Not yet researched'
 with store.db.transaction() as c:c.execute("UPDATE jobs SET title='Application to Example successfully submitted' WHERE id=?",(key,))
 assert leads(store.db)['total']==0 and start(store.db,spawn=False)['selected']==0
 with store.db.transaction() as c:
  assert c.execute('SELECT status FROM jobs WHERE id=?',(key,)).fetchone()[0]!='SUBMITTED'


def test_portal_block_does_not_make_network_request():
 calls=[]
 with httpx.Client(transport=httpx.MockTransport(lambda r:calls.append(r) or httpx.Response(200))) as client:
  with pytest.raises(ValueError,match='unsupported'):read_official('https://linkedin.com/jobs/view/123',client)
 assert calls==[]


def test_actual_official_jobposting_extraction(monkeypatch):
 monkeypatch.setattr('job_agent.email_research.public_url',lambda url:url)
 data={'@type':'JobPosting','title':'Frontend Engineer','description':'Build accessible Angular interfaces and APIs. '*10,'hiringOrganization':{'name':'Example'}}
 body='<script type="application/ld+json">'+json.dumps(data)+'</script>'
 with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,text=body))) as client:
  result,url=read_official('https://careers.example.com/job/123',client)
 assert result['title']=='Frontend Engineer' and result['hiringOrganization']['name']=='Example'


def test_research_queues_are_bounded_and_persist_failure(tmp_path):
 store,engine,key=prepared_store(tmp_path)
 with store.db.transaction() as c:
  c.execute("UPDATE jobs SET discovery_detail=?,application_url='https://linkedin.com/jobs/view/123',canonical_application_url=NULL WHERE id=?",(json.dumps({'evidence':{'origin':'received_alert','metadata_only':True}}),key))
 run=start(store.db,spawn=False);assert run['selected']==1
 with httpx.Client(transport=httpx.MockTransport(lambda r:pytest.fail('Portal access must not be attempted'))) as client:assert execute(store.db,run['run_id'],client)['processed']==1
 assert start(store.db,spawn=False)['selected']==0
 with store.db.transaction() as c:
  row=c.execute("SELECT status,attempts,blocker FROM m2d_tasks WHERE category='EMAIL_OFFICIAL_JD'").fetchone()
 assert row['status']=='BLOCKED' and row['attempts']==1 and 'unsupported' in row['blocker']


def test_retrieved_jd_updates_actual_title_location_and_fit(tmp_path,monkeypatch):
 store,engine,key=prepared_store(tmp_path)
 with store.db.transaction() as c:c.execute("UPDATE jobs SET discovery_detail=?,application_url='https://careers.example.com/jobs/123',canonical_application_url=NULL WHERE id=?",(json.dumps({'evidence':{'origin':'received_alert','metadata_only':True}}),key))
 monkeypatch.setattr('job_agent.email_research.public_url',lambda url:url)
 data={'@type':'JobPosting','title':'Senior Frontend Engineer','description':'Requirements\nAngular and TypeScript are required.\nResponsibilities\nBuild accessible interfaces and APIs. '*5,'hiringOrganization':{'name':'Example'},'jobLocation':{'address':{'addressLocality':'Noida','addressCountry':'India'}}}
 body='<script type="application/ld+json">'+json.dumps(data)+'</script>'
 run=start(store.db,spawn=False)
 with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,text=body))) as client:execute(store.db,run['run_id'],client)
 with store.db.transaction() as c:job=dict(c.execute('SELECT * FROM jobs WHERE id=?',(key,)).fetchone())
 assert job['title']=='Senior Frontend Engineer' and job['location']=='Noida, India'
 assert job['match_score']>0 and 'angular' in json.loads(job['required_skills'])
 assert not json.loads(job['discovery_detail'])['evidence']['metadata_only']

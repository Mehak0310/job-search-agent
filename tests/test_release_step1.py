"""Sanitised structural fixtures from the four observed received-alert formats."""
import base64,json,socket
import httpx
import pytest
from fastapi.testclient import TestClient
from job_agent.alert_extraction import extract_alert,exact_vacancy_url,PARSER_VERSION
from job_agent.alert_redirects import AlertRedirectResolver,public_target
from job_agent.gmail_local import message_from_api
from job_agent.m2d_models import EmailExportMessage
from job_agent.m2d import M2DEngine,GmailExportAdapter,canonical_url
from job_agent.database import Database
from job_agent.email_opportunities import sync_email_opportunities
from job_agent.service import JobService
from job_agent.main import create_app


def mail(body,mid='m1',domain='glassdoor.com'):
    return EmailExportMessage(message_id=mid,received_at='2026-10-15T01:00:00Z',sender_domain=domain,subject='Your job alert',body=body)


def test_actual_wrapper_classes_and_generic_rejection():
    hirist='https://postoffice.hirist.tech/CL0/https:%2F%2Fwww.hirist.tech%2Fj%2Fsample-frontend-engineer-123456%3Fref%3Demail/1/opaque/opaque'
    assert exact_vacancy_url(hirist)=='https://www.hirist.tech/j/sample-frontend-engineer-123456'
    naukri='https://www.naukri.com/jd/job-listings-react-lead-example-noida-121026000001?xp=1&amp;src=email'
    assert exact_vacancy_url(naukri).endswith('121026000001')
    glass='https://www.glassdoor.co.in/partner/jobListing.htm?jobListingId=1000000001&userValidationKey=synthetic-only'
    direct='https://www.glassdoor.co.in/job-listing/react-engineer-example.htm?jl=1000000001'
    assert canonical_url(exact_vacancy_url(glass))==canonical_url(exact_vacancy_url(direct))
    assert exact_vacancy_url('https://www.glassdoor.co.in/job-listing/api/rjtRedirect?loc=India') is None
    assert exact_vacancy_url('https://www.naukri.com/mnjuser/homepage') is None
    assert exact_vacancy_url('https://postoffice.hirist.tech/CL0/https:%2F%2Fevil.test%2Fj%2Frole-123456/1/x') is None


def test_mime_transfer_already_decoded_and_quoted_export():
    def raw(body):
        return {'id':'m','internalDate':'1792026000000','labelIds':['INBOX','UNREAD'],'payload':{'mimeType':'text/html','headers':[{'name':'Content-Transfer-Encoding','value':'quoted-printable'}],'body':{'data':base64.urlsafe_b64encode(body.encode()).decode()}}}
    decoded=message_from_api(raw('<a href="https://in.indeed.com/viewjob?jk=abcdef1234">UI Engineer</a>'))
    assert '?jk=abcdef1234' in decoded.body and decoded.labels==['INBOX','UNREAD']
    exported=message_from_api(raw('<a href=3D"https://in.indeed.com/viewjob?jk=3Dabcdef1234">UI Engineer</a>'))
    assert '?jk=abcdef1234' in exported.body
    literal=message_from_api(raw('A job description mentions Content-Type: without MIME headers.'))
    assert 'Content-Type:' in literal.body


def test_glassdoor_card_fields_and_duplicate_links():
    body='<a href="https://www.glassdoor.co.in/partner/jobListing.htm?jobListingId=1000000001"><span>Example</span><span>4.1 &#9733;</span><p>Senior Frontend Engineer</p><p>Noida</p><p>3d</p></a>'
    parsed=extract_alert(mail(body+body))
    assert len(parsed['vacancies'])==1 and parsed['duplicates']>=1
    lead=parsed['vacancies'][0]
    assert lead.company=='Example' and lead.title=='Senior Frontend Engineer' and lead.location=='Noida'
    assert not hasattr(lead,'published_at')  # Relative age in received mail is not a posting date.


def global_dns(*args,**kwargs):return [(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',443))]


def test_safe_bounded_redirect_and_cache(tmp_path):
    db=Database(tmp_path/'state.sqlite3');calls=[]
    def handler(req):
        calls.append(req.url.host)
        return httpx.Response(302,headers={'location':'https://in.indeed.com/viewjob?jk=abcdef1234&utm_source=mail'})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        resolver=AlertRedirectResolver(db,client=client,dns=global_dns)
        assert resolver('https://engage.indeed.com/f/a/opaque')=='https://in.indeed.com/viewjob?jk=abcdef1234'
        assert resolver('https://engage.indeed.com/f/a/opaque') and len(calls)==1
        assert resolver.cache_hits==1
    for destination in ['https://127.0.0.1/','http://www.naukri.com/','https://user:pass@www.naukri.com/','https://www.naukri.com/login','https://evil.test/']:
        with pytest.raises(ValueError):public_target(destination,global_dns)
    with pytest.raises(ValueError,match='non_public'):
        public_target('https://www.naukri.com/durl/x',lambda *a,**k:[(2,1,6,'',('127.0.0.1',443))])


def test_unresolved_named_lead_is_honest_and_visible(tmp_path):
    db=Database(tmp_path/'state.sqlite3');engine=M2DEngine(db);engine.seed()
    message=mail('<a href="https://engage.indeed.com/f/a/opaque">UI Engineer - Angular</a>',domain='jobalert.indeed.com')
    GmailExportAdapter(engine).ingest([message])
    assert sync_email_opportunities(db)['created']==1
    service=JobService(db);result=service.list_jobs(source='gmail',page=1,page_size=10);job=result['items'][0]
    assert job['company'] is None and job['location'] is None and job['published_at'] is None and job['application_url'] is None
    assert job['card']['fit_label']=='Needs verification' and job['card']['next_action_owner']=='Agent research'
    assert service.set_status(job['id'],'SHORTLISTED')
    assert sync_email_opportunities(db)['created']==0


def test_exact_leads_normal_api_and_profile_rescore(tmp_path):
    app=create_app(tmp_path/'state.sqlite3')
    with TestClient(app) as client:
        engine=app.state.m2d
        message=mail('<a href="https://www.naukri.com/jd/job-listings-react-lead-example-noida-121026000001">React Lead</a>',domain='naukri.com')
        GmailExportAdapter(engine).ingest([message]);sync_email_opportunities(engine.db)
        data=client.get('/api/jobs?source=gmail&page=1&page_size=10').json();assert data['total']==1
        assert data['items'][0]['listing_kind']=='EMAIL' and data['items'][0]['card']['vacancy_url']
        assert client.get('/api/jobs?kind=LIVE&page=1&page_size=10').json()['total']==0
        profile=client.get('/api/profile').json();assert client.put('/api/profile',json=profile).status_code==200
        with engine.db.transaction() as conn:assert not conn.execute('pragma foreign_key_check').fetchall()


def test_month_precision_never_rounds_experience_up():
    from datetime import date
    from job_agent.tenure import tenure_bounds
    result=tenure_bounds('2018-06',date(2025,8,16))
    assert result['minimum_complete_months']==85 and result['maximum_complete_months']==86
    assert result['maximum_complete_months']<8*12


def test_http_failure_cached_without_network_and_replay_keeps_timestamp(tmp_path):
    from job_agent.alert_redirects import CachedAlertResolver
    db=Database(tmp_path/'state.sqlite3');engine=M2DEngine(db);engine.seed();calls=[]
    with httpx.Client(transport=httpx.MockTransport(lambda req:(calls.append(req.url.host) or httpx.Response(403)))) as client:
        resolver=AlertRedirectResolver(db,client=client,dns=global_dns)
        assert resolver('https://engage.indeed.com/f/a/opaque') is None
        assert resolver.last_error=='tracking_http_403'
    cached=CachedAlertResolver(db)
    message=mail('<a href="https://engage.indeed.com/f/a/opaque">UI Engineer</a>',domain='indeed.com')
    adapter=GmailExportAdapter(engine,cached);adapter.ingest([message]);sync_email_opportunities(db)
    with db.transaction() as conn:first=conn.execute('select observed_at from job_observations').fetchone()[0]
    adapter.ingest([message],reprocess=True);assert sync_email_opportunities(db)['created']==0
    with db.transaction() as conn:
        assert conn.execute('select observed_at from job_observations').fetchone()[0]==first
        assert 'tracking_http_403' in conn.execute('select discovery_detail from jobs').fetchone()[0]
    assert len(calls)==1 and cached.requests==0


def test_html_subject_does_not_turn_generic_tracking_into_vacancy():
    message=mail('<a href="https://engage.indeed.com/f/a/opaque">Manage alerts</a>',domain='indeed.com')
    message.subject='Ten UI Engineer vacancies'
    assert not extract_alert(message)['unresolved']


def test_employer_cache_entity_scope_and_expiry(tmp_path):
    from datetime import datetime,timedelta,timezone
    from job_agent.employer_evidence import cached_employer,cache_employer
    path=tmp_path/'employer.json';at=datetime(2026,10,16,tzinfo=timezone.utc)
    cache_employer(path,entity='Example group',scope='remote group',headcount=1200,as_of='2026-01-31',url='https://example.com/report',at=at)
    assert cached_employer(path,'Example group','remote group',at)['headcount']==1200
    assert cached_employer(path,'Example India','remote group',at) is None
    assert cached_employer(path,'Example group','India subsidiary',at) is None
    assert cached_employer(path,'Example group','remote group',at+timedelta(days=91)) is None


def test_canonical_provenance_and_different_requisitions(tmp_path):
    from job_agent.models import JobInput
    db=Database(tmp_path/'state.sqlite3');service=JobService(db);engine=M2DEngine(db);engine.seed()
    url='https://www.naukri.com/jd/job-listings-react-lead-example-noida-121026000001'
    service.import_rows([JobInput(source='fixture',source_job_id='one',company='Example',title='React Lead',location='Noida',description='React',skills=['react'],application_url=url)])
    adapter=GmailExportAdapter(engine)
    adapter.ingest([mail(f'<a href="{url}">React Lead</a>',mid='first',domain='naukri.com')])
    assert sync_email_opportunities(db)['linked_existing']==1
    adapter.ingest([mail(f'<a href="{url}">React Lead</a>',mid='second',domain='naukri.com')])
    assert sync_email_opportunities(db)['created']==0
    second=url.replace('121026000001','121026000002')
    adapter.ingest([mail(f'<a href="{second}">React Lead</a>',mid='third',domain='naukri.com')])
    assert sync_email_opportunities(db)['created']==1
    with db.transaction() as conn:
        assert conn.execute('select count(*) from jobs').fetchone()[0]==2
        assert conn.execute("select count(*) from source_references where source='gmail'").fetchone()[0]==3

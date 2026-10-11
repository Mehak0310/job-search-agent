import threading,time,httpx
from datetime import datetime,timedelta,timezone
from job_agent.freshness import *
from job_agent.public_connectors import RemoteOKConnector,WWRConnector,PublicReader,RequestBudget
from job_agent.public_connectors import ProviderError
import pytest
from job_agent.discovery_models import DiscoverySettings,SourceConfig,metrics
from job_agent.discovery_models import DiscoveryConfig
from job_agent.discovery import Discovery
from job_agent.database import Database
from job_agent.registry import Registry

def reader(payload,content_type="application/json"):
    def handler(request): return httpx.Response(200,content=payload,headers={"content-type":content_type})
    settings=DiscoverySettings(retry_limit=0); counts=metrics()
    return PublicReader(httpx.Client(transport=httpx.MockTransport(handler)),RequestBudget(settings),counts),counts

def test_freshness_boundaries_aliases_locations(monkeypatch):
    now=datetime(2026,10,10,tzinfo=timezone.utc)
    assert freshness_weight(.5)==1 and freshness_weight(2)==.98 and freshness_weight(8)==.95
    assert freshness_weight(20)==.9 and freshness_weight(30)==.8 and freshness_weight(100)==.6 and freshness_weight(200)==.35 and freshness_weight(None)==0
    stamp,confidence=utc_timestamp("2026-10-09T20:00:00Z"); assert confidence=="HIGH" and age_hours(stamp,now)==4
    assert utc_timestamp("2026-10-09")[1]=="DATE_ONLY" and utc_timestamp(None)==(None,"UNKNOWN")
    assert utc_timestamp("bad")[1]=="INVALID" and utc_timestamp("2999-01-01T00:00:00Z")[1]=="INVALID_FUTURE"
    assert utc_timestamp(1_700_000_000_000)[0]
    assert discovery_priority(80,"ELIGIBLE",stamp,now)>discovery_priority(80,"UNKNOWN",None,now)
    assert normalize_skills(["JS","React.js","C Sharp"])==["c#","javascript","react"]
    assert location_bucket("Gurgaon, India")=="GURUGRAM" and location_bucket("Greater Noida") == "GREATER_NOIDA"
    assert location_bucket("Noida") == "NOIDA" and location_bucket("Mohali") == "MOHALI" and location_bucket("Chandigarh")=="CHANDIGARH"
    assert location_bucket("New Delhi")=="DELHI_NCR" and location_bucket("India","ELIGIBLE","remote")=="REMOTE_INDIA"
    assert location_bucket("Bengaluru","ELIGIBLE")=="OTHER_INDIA" and location_bucket("Remote")=="UNKNOWN"

def test_remoteok_and_wwr_feeds():
    data=b'[{"legal":"meta"},{"id":"7","company":"Acme","position":"React Engineer","description":"Requirements\\nReact required","location":"Worldwide","url":"https://remoteok.com/remote-jobs/7","epoch":1700000000}]'
    r,c=reader(data); source=SourceConfig(id="rok",provider="remoteok",company="Remote OK",board="all")
    batch=RemoteOKConnector().fetch(source,r,{}); job,url,evidence=RemoteOKConnector().normalize(source,batch.records[0]); assert job.title=="React Engineer" and evidence["published_at"] and c["records_fetched"]==1
    xml=b'<rss><channel><item><title>Acme: Angular Lead</title><guid>g1</guid><link>https://weworkremotely.com/remote-jobs/g1</link><pubDate>Thu, 09 Oct 2026 10:00:00 +0000</pubDate><description>Requirements Angular required</description></item></channel></rss>'
    r,c=reader(xml,"application/rss+xml"); source=SourceConfig(id="wwr",provider="wwr",company="We Work Remotely",board="all")
    batch=WWRConnector().fetch(source,r,{}); job,url,evidence=WWRConnector().normalize(source,batch.records[0]); assert job.company=="Acme" and job.title=="Angular Lead" and evidence["timestamp_provenance"]=="rss.pubDate"
    r,_=reader(b"not xml","application/rss+xml")
    with pytest.raises(ProviderError,match="invalid_feed_response"): WWRConnector().fetch(source,r,{})

def test_pagination_combined_filters(client,record):
    rows=[record|{"source_job_id":str(i),"application_url":f"https://example.com/{i}","title":f"React Engineer {i}"} for i in range(23)]
    client.post('/api/import',files={"file":("jobs.json",__import__('json').dumps(rows),"application/json")})
    first=client.get('/api/jobs?page=1&page_size=10&title=React&sort=score_desc').json(); second=client.get('/api/jobs?page=2&page_size=10&title=React').json()
    assert first["total"]==23 and first["pages"]==3 and first["has_next"] and not first["has_previous"]
    assert len(second["items"])==10 and {x['id'] for x in first['items']}.isdisjoint(x['id'] for x in second['items'])
    assert client.get('/api/jobs?page=4&page_size=10&title=React').json()['items']==[]
    assert client.get('/api/overview').json()['total']==23
    app=client.app
    with app.state.discovery.db.transaction() as conn:
        stamp=(datetime.now(timezone.utc)-timedelta(hours=2)).isoformat()
        conn.execute("UPDATE jobs SET published_at=?,location_bucket='GURUGRAM',required_experience_min=5,required_experience_max=8,required_skills='[\"react\",\"typescript\"]'",(stamp,))
    base='/api/jobs?page=1&page_size=10'
    assert client.get(base+'&freshness=6h').json()['total']==23
    assert client.get(base+'&freshness=unknown').json()['total']==0
    assert client.get(base+'&location_bucket=GURUGRAM,NOIDA').json()['total']==23
    assert client.get(base+'&experience=5-8').json()['total']==23
    assert client.get(base+'&experience=unknown').json()['total']==0
    assert client.get(base+'&skills=JS,React.js&skill_mode=any').json()['total']==23
    assert client.get(base+'&skills=React,TypeScript&skill_mode=all').json()['total']==23
    for sort in ('newest','priority','updated'): assert client.get(base+'&sort='+sort).status_code==200

def test_bounded_concurrent_fetch_serialized_writes(tmp_path):
    lock=threading.Lock(); active=peak=0
    def handler(request):
        nonlocal active,peak
        board=request.url.path.split('/')[-2]
        with lock: active+=1; peak=max(peak,active)
        time.sleep(.08)
        with lock: active-=1
        job={"id":board,"title":"React Engineer","location":{"name":"India"},"absolute_url":f"https://example.com/{board}","content":"Requirements React required"}
        return httpx.Response(200,json={"jobs":[job],"meta":{"total":1}})
    sources=[SourceConfig(id=f"s{i}",provider="greenhouse",company=f"C{i}",board=f"b{i}",enabled=True) for i in range(4)]
    cfg=DiscoveryConfig(settings=DiscoverySettings(concurrency_limit=2,cooldown_seconds=0,retry_limit=0),sources=sources)
    db=Database(tmp_path/'c.db');Registry(db).sync(cfg);d=Discovery(db,cfg.settings,lambda:httpx.Client(transport=httpx.MockTransport(handler)))
    started=time.monotonic(); result=d.execute(d.claim()); elapsed=time.monotonic()-started; d.close()
    assert result['metrics']['new_jobs']==4 and result['status']=='COMPLETED' and peak==2 and elapsed<.6

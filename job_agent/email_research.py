"""Bounded, explicit alert research. Unsupported portal access is never hidden."""
import argparse,json,re,subprocess,sys,uuid,time,sqlite3
from datetime import datetime,timedelta,timezone
from urllib.parse import urlsplit,urljoin,unquote
from html.parser import HTMLParser
import httpx
from .database import Database,now
from .runtime_policy import digest
from .browser_forms import public_url

PORTALS={'linkedin.com','www.linkedin.com','naukri.com','www.naukri.com','glassdoor.co.in','www.glassdoor.co.in','glassdoor.com','www.glassdoor.com','hirist.tech','www.hirist.tech','wellfound.com','foundit.in','www.foundit.in'}

def receipt_title(value):
    """Receipt subjects are history, never evidence of a new vacancy or submission."""
    return bool(re.search(r'\bapplication\b.*\b(?:submitted|received|confirmation)\b|thank you for (?:applying|your application)',value or '',re.I))


def proper_title(value):
    text=(value or '').strip()
    normalized=re.sub(r'[^a-z0-9]+',' ',text.casefold()).strip()
    generic={'open job','open job alert','view job','apply','apply now','job alert','new job','new jobs','role needs verification','unknown'}
    return text if text and not receipt_title(text) and normalized not in generic and not re.match(r'https?://',text,re.I) else None


def leads(db,page=1):
    from .priority_queue import lead_priorities
    priorities=lead_priorities(db)
    with db.transaction() as conn:
        rows=[dict(r) for r in conn.execute("SELECT id,title,company,application_url,canonical_application_url,description,discovery_detail FROM jobs WHERE json_extract(discovery_detail,'$.evidence.origin')='received_alert' AND COALESCE(json_extract(discovery_detail,'$.evidence.retracted'),0)=0 ORDER BY last_seen DESC,id")]
        metadata={r['message_id']:dict(r) for r in conn.execute('SELECT * FROM email_message_metadata')}
        observations={r['job_key']:json.loads(r['evidence']) for r in conn.execute("SELECT job_key,evidence FROM job_observations WHERE stream='GMAIL'")}
        refs={r['job_id']:r['source_job_id'] for r in conn.execute("SELECT job_id,source_job_id FROM source_references WHERE source='gmail'")}
        tasks={r['job_key']:dict(r) for r in conn.execute("SELECT * FROM m2d_tasks WHERE kind='VERIFICATION' AND category='EMAIL_OFFICIAL_JD'")}
        official=[dict(r) for r in conn.execute("SELECT title,company,application_url FROM jobs WHERE length(description)>300 AND COALESCE(json_extract(discovery_detail,'$.evidence.metadata_only'),0)=0")]
    items=[]
    for row in rows:
        if receipt_title(row['title']):continue
        title=proper_title(row['title']);url=row['canonical_application_url'] or row['application_url'];task=tasks.get(row['id']);status=task['status'] if task else 'NOT_QUEUED';checkpoint=json.loads(task['checkpoint'] or '{}') if task else {}
        named=bool(title and url)
        state={'NOT_QUEUED':'Not yet researched','PENDING':'Queued for research','RUNNING':'Researching now','COMPLETED':'Official job description retrieved','BLOCKED':'Access or identity blocked','FAILED':'Research attempt failed','PARTIAL':'Needs another supported source'}.get(status,status)
        action=task['blocker'] if task and task['blocker'] else 'Click Research next 5 alert links to start bounded research; no automatic completion time is promised.'
        if not url:state='Unresolved alert link';action='This alert has no permitted exact job URL. Agent must resolve the received link before it can be a researched job.'
        candidates=[{'title':o['title'],'company':o['company'],'url':o['application_url']} for o in official if title and row['company'] and o['title'].casefold()==title.casefold() and (o['company'] or '').casefold()==row['company'].casefold()][:3]
        items.append({'id':row['id'],'title':title,'company':row['company'],'url':url,'research_state':state,'next_action':action,'researched_at':task['updated_at'] if task else None,'named':named,'official_candidates':candidates,'status':status})
        evidence=json.loads(row['discovery_detail'] or '{}').get('evidence',{});obs=observations.get(row['id'],{})
        message_id=refs.get(row['id']) or obs.get('message_id') or next(iter(evidence.get('source_message_refs',[])),None)
        message=metadata.get(message_id,{})
        from urllib.parse import quote
        restricted=(urlsplit(url or '').hostname or '') in PORTALS
        verified=bool(status=='COMPLETED' and evidence.get('official_jd_url') and not evidence.get('metadata_only',True) and not restricted)
        items[-1].update(message_id=message_id,sender=message.get('sender'),subject=message.get('subject'),received_at=message.get('received_at') or obs.get('received_at'),gmail_url='https://mail.google.com/mail/u/0/#all/'+quote(message_id,safe='') if message_id else None,
                         verification='VERIFIED_OFFICIAL_JD' if verified else 'RESTRICTED_SOURCE' if restricted else 'NEEDS_VERIFICATION',duplicate_status='IMPORTED_OPPORTUNITY',opportunity_id=row['id'],can_import=verified,
                         metadata_blocker=None if message else 'Original sender and subject were not retained by the older intake; open the received message. No header invented.')
    for item in items:
        priority=priorities.get(item['id'],{})
        item.update(message_category=priority.get('category','UNCLASSIFIED_RECEIVED_LEAD'),priority_tier=priority.get('tier',0),deadline=priority.get('deadline'),priority_reason=priority.get('reason','Received alert needs classification/verification; no direct recruiter conversation inferred.'))
    items.sort(key=lambda item:(-item['priority_tier'],item['deadline'] or '9999',not item['named'],item['title'] or '',item['id']))
    for position,item in enumerate(items,1):item['queue_position']=position
    total=len(items);page=max(1,page);start=(page-1)*20
    return {'items':items[start:start+20],'total':total,'named':sum(v['named'] for v in items),'unresolved':sum(not v['named'] for v in items),'running':sum(v['status'] in {'PENDING','RUNNING'} for v in items),'page':page,'pages':max(1,(total+19)//20)}


def start(db,spawn=True,job_id=None):
    selected=[];run_id=uuid.uuid4().hex
    with db.transaction() as conn:
        rows=conn.execute("SELECT id,title,canonical_application_url,application_url,first_seen FROM jobs WHERE json_extract(discovery_detail,'$.evidence.origin')='received_alert' AND COALESCE(json_extract(discovery_detail,'$.evidence.retracted'),0)=0 ORDER BY CASE WHEN COALESCE(canonical_application_url,application_url,'')='' THEN 1 ELSE 0 END,last_seen DESC,id").fetchall()
        from .priority_queue import lead_priorities
        priority=lead_priorities(db)
        known={r[0] for r in conn.execute("SELECT job_key FROM m2d_tasks WHERE category='EMAIL_OFFICIAL_JD'")}
        rows=[r for r in rows if r['id'] not in known]
        rows=sorted(rows,key=lambda r:(-priority.get(r['id'],{}).get('tier',0),priority.get(r['id'],{}).get('deadline') or '9999',r['id']))
        aged=[r for r in rows if r['first_seen'] and r['first_seen']<(datetime.now(timezone.utc)-timedelta(days=1)).isoformat()]
        if len(rows)>5 and aged:
            oldest=min(aged,key=lambda r:(r['first_seen'],r['id']))
            if oldest not in rows[:5]:rows.remove(oldest);rows.insert(4,oldest)
        for row in rows:
            if job_id and row['id']!=job_id:continue
            if receipt_title(row['title']):continue
            key=digest(['alert-detail',row['id']]);prior=conn.execute('SELECT status,attempts,max_attempts FROM m2d_tasks WHERE task_id=?',(key,)).fetchone()
            if prior:continue # Explicit failures/blockers are not blindly retried.
            selected.append(row['id']);stamp=now()
            conn.execute("INSERT INTO m2d_tasks(task_id,kind,job_key,stream,category,payload,status,priority,due_at,attempts,max_attempts,checkpoint,created_at,updated_at) VALUES(?,'VERIFICATION',?,'GMAIL','EMAIL_OFFICIAL_JD',?,'PENDING',30,?,0,3,'{}',?,?)",(key,row['id'],json.dumps({'run_id':run_id,'url':row['canonical_application_url'] or row['application_url']}),stamp,stamp,stamp))
            if len(selected)==5:break
        db.audit(conn,'ALERT_DETAIL_BATCH_QUEUED',{'selected':len(selected),'run_id':run_id})
    if spawn and selected:
        folder=db.path.parent/'email-research';folder.mkdir(exist_ok=True)
        with (folder/'worker.log').open('ab') as log:subprocess.Popen([sys.executable,'-m','job_agent.email_research','--db',str(db.path.resolve()),'--run',run_id],stdin=subprocess.DEVNULL,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    return {'selected':len(selected),'run_id':run_id}


def import_lead(db,identifier):
    """Existing canonical alert opportunities are linked, never duplicated or verified here."""
    page=1
    while True:
        result=leads(db,page)
        item=next((r for r in result['items'] if r['id']==identifier),None)
        if item:
            if not item['can_import']:raise ValueError('official_job_verification_required')
            return {'state':'ALREADY_IMPORTED','job_id':item['opportunity_id'],'created':False,'provenance_preserved':True}
        if page>=result['pages']:raise ValueError('lead_not_found')
        page+=1


class JobSchema(HTMLParser):
    def __init__(self):super().__init__();self.active=False;self.parts=[];self.schemas=[]
    def handle_starttag(self,tag,attrs):
        if tag=='script' and dict(attrs).get('type')=='application/ld+json':self.active=True;self.parts=[]
    def handle_data(self,data):
        if self.active:self.parts.append(data)
    def handle_endtag(self,tag):
        if tag=='script' and self.active:
            self.active=False
            try:self.schemas.append(json.loads(''.join(self.parts)))
            except ValueError:pass


def read_official(url,client,limits=None):
    limits=limits or {'requests':0,'deadline':time.monotonic()+45}
    for _ in range(4):
        if limits['requests']>=12 or time.monotonic()>=limits['deadline']:raise ValueError('Bounded research budget reached; remaining source needs a later explicit run')
        parsed=urlsplit(url)
        if re.search(r'unsubscribe|autologin|logout|delete|withdraw|submit|confirm_email|activate|reset_password',unquote(parsed.path+'?'+parsed.query),re.I):raise ValueError('Action link rejected; only public vacancy reads are supported')
        if (urlsplit(url).hostname or '') in PORTALS:raise ValueError('Portal scraping is unsupported; an exact official employer application route is required. No account or CAPTCHA bypass attempted.')
        public_url(url)
        limits['requests']+=1
        with client.stream('GET',url,follow_redirects=False,timeout=max(.1,min(10,limits['deadline']-time.monotonic()))) as response:
            if response.status_code in {301,302,303,307,308}:url=urljoin(url,response.headers.get('location',''));continue
            if response.status_code!=200:raise ValueError('Official source returned HTTP '+str(response.status_code)+'; no job details invented.')
            payload=bytearray()
            for chunk in response.iter_bytes():
                payload.extend(chunk)
                if len(payload)>2*1024*1024:raise ValueError('Job page exceeds bounded response size')
        parser=JobSchema();parser.feed(bytes(payload).decode('utf-8',errors='replace'))
        def find(value):
            if isinstance(value,list):
                for child in value:
                    found=find(child)
                    if found:return found
            elif isinstance(value,dict):
                if value.get('@type')=='JobPosting':return value
                return find(value.get('@graph',[]))
        for schema in parser.schemas:
            result=find(schema)
            if result and result.get('title') and result.get('description'):return result,url
        raise ValueError('Public page has no supported JobPosting description; agent research needs another official source.')
    raise ValueError('Redirect limit reached; no destination was assumed safe')


def execute(db,run_id,client=None):
    from .public_connectors import plain_text
    with db.transaction() as conn:rows=[dict(r) for r in conn.execute("SELECT * FROM m2d_tasks WHERE kind='VERIFICATION' AND category='EMAIL_OFFICIAL_JD' AND status='PENDING' AND json_extract(payload,'$.run_id')=? ORDER BY created_at LIMIT 5",(run_id,))]
    owned=client is None;client=client or httpx.Client(trust_env=False)
    limits={'requests':0,'deadline':time.monotonic()+90}
    try:
        for row in rows:
            with db.transaction() as conn:conn.execute("UPDATE m2d_tasks SET status='RUNNING',attempts=attempts+1,updated_at=? WHERE task_id=?",(now(),row['task_id']))
            try:
                url=json.loads(row['payload']).get('url')
                if not url:raise ValueError('Exact job URL is unavailable; opaque received link needs permitted resolution first.')
                data,source=read_official(url,client,limits)
                if not isinstance(data.get('title'),str) or not isinstance(data.get('description'),str):raise ValueError('Official job schema has unsupported title/description types')
                title=plain_text(data['title'])[:200];description=plain_text(data['description'])
                if len(description)<100:raise ValueError('Official description is insufficient for role assessment')
                organization=data.get('hiringOrganization')
                company=organization.get('name') if isinstance(organization,dict) else None
                if not isinstance(company,str) or not company.strip():company=None
                with db.transaction() as conn:
                    current=conn.execute('SELECT discovery_detail FROM jobs WHERE id=?',(row['job_key'],)).fetchone();detail=json.loads(current[0] or '{}');detail.setdefault('evidence',{}).update(metadata_only=False,official_jd_url=source,official_jd_checked_at=now(),requirements_review_pending=True)
                    if len(description)>20000:raise ValueError('Official JD exceeds supported field size; no partial fit assessment was stored')
                    current_job=dict(conn.execute('SELECT * FROM jobs WHERE id=?',(row['job_key'],)).fetchone())
                    if company:
                        from .models import JobInput
                        from .candidate import CandidateProfile
                        from .classification import extract_requirements,rank
                        from .discovery_store import _write_job
                        addresses=data.get('jobLocation',[])
                        if isinstance(addresses,dict):addresses=[addresses]
                        locations=[]
                        for entry in addresses if isinstance(addresses,list) else []:
                            address=entry.get('address',{}) if isinstance(entry,dict) else {}
                            if isinstance(address,dict):
                                for name in ['addressLocality','addressRegion','addressCountry']:
                                    value=address.get(name)
                                    if isinstance(value,dict):value=value.get('name')
                                    if isinstance(value,str) and value not in locations:locations.append(value)
                        location=', '.join(locations) or current_job['location'] or 'Location not provided'
                        mode='remote' if data.get('jobLocationType')=='TELECOMMUTE' else current_job['work_mode']
                        evidence=extract_requirements(description)|detail['evidence']
                        evidence.update(extract_requirements(description));evidence.update(source_location=location,published_at=data.get('datePosted'))
                        candidate=CandidateProfile.model_validate_json(conn.execute('SELECT config FROM candidate_profiles_v2 WHERE id=1').fetchone()[0])
                        job=JobInput(source='gmail',company=company,title=title,location=location,description=description,work_mode=mode,skills=evidence['mentioned'],application_url=source)
                        match=rank(job,evidence,candidate.search_background(),candidate.search_profile())
                        _write_job(conn,job,row['job_key'],match,source,'gmail',now(),current_job)
                    else:
                        conn.execute('UPDATE jobs SET title=?,description=?,discovery_detail=?,last_verified=?,updated_at=? WHERE id=?',(title,description,json.dumps(detail),now(),now(),row['job_key']))
                    conn.execute("UPDATE m2d_tasks SET status='COMPLETED',blocker='Official JD retrieved; fit, location and employment evidence still require assessment.',checkpoint=?,updated_at=? WHERE task_id=?",(json.dumps({'source_url':source}),now(),row['task_id']))
            except (ValueError,httpx.HTTPError,OSError,sqlite3.IntegrityError) as error:
                reason=str(error) if isinstance(error,ValueError) else type(error).__name__
                with db.transaction() as conn:conn.execute("UPDATE m2d_tasks SET status='BLOCKED',blocker=?,updated_at=? WHERE task_id=?",(reason,now(),row['task_id']))
    finally:
        if owned:client.close()
    return {'processed':len(rows)}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--db',default='data/jobs.sqlite3');parser.add_argument('--run',required=True);args=parser.parse_args();print(json.dumps(execute(Database(args.db),args.run)))

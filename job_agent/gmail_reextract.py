"""Explicit bounded alert re-extraction on the existing durable task queue."""
import hashlib
import json
from datetime import datetime,timedelta,timezone
from .database import now
from .m2d import GmailExportAdapter

from .alert_extraction import PARSER_VERSION
VERSION=PARSER_VERSION
PROVIDERS=('linkedin.com','naukri.com','indeed.com','glassdoor.com','glassdoor.co.in','foundit.in','hirist.tech','instahyre.com','cutshort.io','wellfound.com','weekday.works','iimjobs.com','welcometothejungle.com')


def reextract_interval(engine,reader,start,end,*,max_pages=2,page_size=100):
    if not 1<=max_pages<=5 or not 1<=page_size<=100:raise ValueError('invalid_reextraction_budget')
    for value in (start,end):
        if datetime.fromisoformat(value.replace('Z','+00:00')).tzinfo is None:raise ValueError('timezone_required')
    if datetime.fromisoformat(start.replace('Z','+00:00'))>=datetime.fromisoformat(end.replace('Z','+00:00')):raise ValueError('invalid_interval')
    task_id=hashlib.sha256(f'{VERSION}:{start}:{end}'.encode()).hexdigest()
    engine.enqueue(kind='DISCOVERY',source_id='gmail',stream='GMAIL',category='ALERT_REEXTRACTION',payload={'version':VERSION,'start':start,'end':end},task_id=task_id,max_attempts=20)
    stamp=now();lease=(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat()
    with engine.db.transaction() as conn:
        row=conn.execute('SELECT * FROM m2d_tasks WHERE task_id=?',(task_id,)).fetchone()
        if row['status']=='COMPLETED':return json.loads(row['checkpoint'])|{'reused':True,'task_id':task_id}
        if row['status']=='RUNNING' and row['lease_until']>stamp:raise ValueError('reextraction_in_progress')
        checkpoint=json.loads(row['checkpoint']);conn.execute("UPDATE m2d_tasks SET status='RUNNING',lease_until=?,attempts=attempts+1,updated_at=? WHERE task_id=?",(lease,stamp,task_id))
    checkpoint.setdefault('pages',0);checkpoint.setdefault('messages',0);checkpoint.setdefault('new_observations',0);checkpoint.setdefault('alert_sources',{})
    token=checkpoint.get('next_page_token')
    try:
        for _ in range(max_pages):
            page=reader.read_interval(start,end,token,page_size);messages=page['messages']
            intake=GmailExportAdapter(engine).ingest(messages,import_id=task_id,limit=len(messages) or 1,interval_end=end,reprocess=True)
            for message in messages:
                domain=message.sender_domain or ''
                provider=next((value for value in PROVIDERS if domain==value or domain.endswith('.'+value)),None)
                if provider:
                    item=checkpoint['alert_sources'].setdefault(provider,{'messages':0,'sender_domains':[]})
                    item['messages']+=1
                    if domain not in item['sender_domains']:item['sender_domains'].append(domain)
            token=page['next_page_token'];checkpoint.update(next_page_token=token,status='PARTIAL' if token else 'COMPLETED',version=VERSION,interval_start=start,interval_end=end)
            checkpoint['pages']+=1;checkpoint['messages']+=len(messages);checkpoint['new_observations']+=intake['vacancies']
            with engine.db.transaction() as conn:conn.execute('UPDATE m2d_tasks SET checkpoint=?,updated_at=? WHERE task_id=?',(json.dumps(checkpoint),now(),task_id))
            if not token:break
        engine.finish_task(task_id,status=checkpoint['status'],checkpoint=checkpoint)
        return checkpoint|{'reused':False,'task_id':task_id}
    except Exception as error:
        engine.finish_task(task_id,status='PARTIAL',checkpoint=checkpoint,blocker=type(error).__name__)
        raise

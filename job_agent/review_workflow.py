"""Review progress and explicit reusable user answers, private and local."""
import json,re
from .application_answers import approved_facts,answer,question_key
from .document_manifest import resolve_approved_document
from .browser_store import BrowserStore
from .runtime_policy import digest


def pending_questions(db,identifier):
    store=BrowserStore(db);item=store.get(identifier)
    path=db.path.parent/'browser-applications'/(identifier+'.json')
    if not path.is_file():return []
    saved=json.loads(path.read_text(encoding='utf-8'))
    if saved.get('stale') or item['session_health']=='LOST':return []
    profile,facts,_,_=approved_facts(db)
    with db.transaction() as conn:job=dict(conn.execute('SELECT * FROM jobs WHERE id=?',(item['job_id'],)).fetchone())
    questions=[];seen=set()
    for field in saved.get('inventory',[]):
        from .preparation_policy import human_control
        if human_control(field):continue
        label=field.get('group') if field['type']=='radio' else field['label']
        label=label or field['label']
        if not field.get('visible') or not field.get('required') or field.get('disabled') or not label:continue
        if field['type'] in {'checkbox','file','hidden','submit','button','password'} or re.search(r'consent|attest|certif|privacy|gender|ethnic|race|veteran|disabil',label,re.I):continue
        if field['type']=='radio' and any(f['type']=='radio' and f['name']==field['name'] and f.get('value') for f in saved['inventory']):continue
        if field.get('value') not in ('',None,False,[]):continue
        value,_=answer({**field,'label':label},facts,profile,saved.get('full_jd',job['description']),job['title'],job['company'],'india' in (job['location'] or '').casefold())
        if value is not None:continue
        # A known fact with an unsupported control/unit is an agent task, not a new personal question.
        known_patterns={'expected_compensation':r'expected.*(?:salary|ctc|compensation)|salary expectation','current_compensation':r'current.*(?:salary|ctc|compensation)','notice_period':r'notice period|how soon.*join','country':r'^(?!.*(?:citizen|nationality|birth|passport|eligible|authoriz|authoris)).*country','current_company':r'(?:current|most recent).*(?:employer|company)','current_title':r'(?:current|most recent).*job title','surname_fallbacks':r'last name|surname|family name'}
        if any(key in facts and re.search(pattern,label,re.I) for key,pattern in known_patterns.items()):continue
        key=question_key(label,job['company'])
        if key in seen:continue
        seen.add(key)
        options=field.get('options',[])
        if field['type']=='radio':options=[{'label':f['label'],'value':f['label'],'disabled':False} for f in saved['inventory'] if f['type']=='radio' and f['name']==field['name']]
        questions.append({'key':key,'label':label,'instructions':field.get('instructions',''),'options':[o['label'] for o in options if not o.get('disabled') and o['label']],'max_length':field.get('max_length',-1),'company':job['company']})
    return questions


def save_answers(db,identifier,values):
    from .service import JobService
    questions={q['key']:q for q in pending_questions(db,identifier)}
    answers={};scopes={}
    for value in values:
        q=questions.get(value['key']);body=value['value'].strip()
        if not q or not body:raise ValueError('question_changed_or_answer_empty')
        if q['options'] and body not in q['options']:raise ValueError('answer_not_in_options')
        if q['max_length']>0 and len(body)>q['max_length']:raise ValueError('answer_exceeds_character_limit')
        # Exact question and employer scope are the conservative default.
        key=question_key(q['label'],q['company'],'shared' if value.get('reuse') else 'employer')
        if value.get('reuse') and re.search(r'previous|ever worked|consult|restrict|conflict|sponsor|authoriz',q['label'],re.I):raise ValueError('employer_specific_answer_cannot_be_shared')
        answers[key]=body
        scopes[key]='shared' if value.get('reuse') else 'employer:'+q['company'].casefold().strip()
    result=JobService(db).record_confirmed_application_answers(answers,'Explicit portal answer confirmation; application '+identifier,scopes)
    from .reconciliation_r2 import reconcile
    result['reconciliation']=reconcile(db)
    return result


def resolution_report(db,identifier):
    item=BrowserStore(db).get(identifier)
    path=db.path.parent/'browser-applications'/(identifier+'.json')
    if not path.is_file():return {'fields':[],'state':'NEEDS_INSPECTION','reason':'No inspected inventory; inspect the employer form before filling.'}
    saved=json.loads(path.read_text(encoding='utf-8'))
    with db.transaction() as conn:job=dict(conn.execute('SELECT * FROM jobs WHERE id=?',(item['job_id'],)).fetchone())
    profile,facts,sources,_=approved_facts(db)
    from .preparation_policy import human_control
    result=[]
    for field in saved.get('inventory',[]):
        if not field.get('required') or not field.get('visible') or field.get('disabled'):continue
        label=field.get('group') if field['type']=='radio' else field['label'];label=label or field['label']
        value,key=answer({**field,'label':label},facts,profile,saved.get('full_jd',job['description']),job['title'],job['company'],'india' in (job['location'] or '').casefold())
        state='HUMAN_ONLY' if human_control(field) else 'RESOLVED' if value is not None else 'UNKNOWN'
        if saved.get('stale') or item['session_health']=='LOST':state='NEEDS_INSPECTION'
        elif field['type'] in {'file','hidden','button','submit','password','checkbox'}:state='HUMAN_ONLY' if human_control(field) else 'AGENT_CONTROL'
        elif value is not None and field.get('options') and str(value) not in {str(o.get('label')) for o in field['options'] if not o.get('disabled')}:state='AGENT_CONTROL'
        if not key:
            patterns={'country':r'^(?!.*(?:citizen|nationality|birth|passport|eligible|authoriz|authoris)).*country','notice_period':r'notice period','expected_compensation':r'expected.*(?:salary|compensation|ctc)|salary expectation','current_company':r'(?:current|most recent).*(?:company|employer)'}
            key=next((k for k,p in patterns.items() if re.search(p,label,re.I)),None)
        provenance=sources.get(key,{}) if isinstance(key,str) else key
        if state=='UNKNOWN' and provenance and provenance.get('resolution')=='CONFLICT':state='CONFLICT'
        result.append(dict(label=label,state=state,value=value,provenance=provenance,explanation='Retrieved from approved fact evidence; employer field still requires read-back.' if state=='RESOLVED' else 'Saved inventory requires current inspection.' if state=='NEEDS_INSPECTION' else 'Control requires agent inspection; no new personal answer requested.' if state=='AGENT_CONTROL' else 'Human decision required.' if state=='HUMAN_ONLY' else 'No compatible approved personal fact found.'))
    return {'fields':result,'profile_version':profile.get('version'),'form_changed':False}


def progress(db):
    from .browser_workers import BrowserWorkers
    workers=BrowserWorkers(db)
    # Metadata-only crash recovery. This never launches a browser or retries a write.
    workers.recover_expired();operations=workers.list()
    store=BrowserStore(db)
    with db.transaction() as conn:
        batches=[dict(r) for r in conn.execute('SELECT * FROM browser_batches ORDER BY created_at DESC LIMIT 5')]
    for batch in batches:
        rows=store.list(batch['id'],include_history=True)
        operation=next((w for w in operations if w['batch_id']==batch['id']),{})
        if operation:
            ids=set(operation['application_ids']);rows=[r for r in store.list(include_history=True) if r['id'] in ids]
        batch.update(total=len(rows),processed=sum(r['state']!='PREPARING' for r in rows),ready=sum(r['state']=='READY_FOR_USER_REVIEW' for r in rows),needs_answers=sum(r['state']=='NEEDS_USER_ANSWER' for r in rows),agent_checks=sum(r['state'] in {'ERROR','SESSION_LOST','NEEDS_EMPLOYER_CHECK','NEEDS_LOGIN'} for r in rows),application_ids=[r['id'] for r in rows],worker_state=operation.get('state'),worker_owner=operation.get('owner'),heartbeat_at=operation.get('heartbeat_at'),phase=operation.get('phase'),updated_at=operation.get('updated_at'),retry_condition=operation.get('retry_condition'))
    with db.transaction() as conn:profile=json.loads(conn.execute('SELECT config FROM candidate_profiles_v2 ORDER BY version DESC LIMIT 1').fetchone()[0])
    manifest_path=db.path.parent/'documents'/'manifest.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.is_file() else {'documents':[]}
    documents=[]
    for item in manifest.get('documents',[]):
        from .private_config import document_role
        if document_role(item,db.path.parent) not in {'resume','cover_letter'}:continue
        try:resolve_approved_document(item,db.path.parent);available=True
        except ValueError:available=False
        documents.append({'name':item['canonical_name'],'available':available,'sha256':item['sha256']})
    active=next((w for w in operations if w['state'] in {'QUEUED','RUNNING'}),None)
    selected=active.get('batch_id') if active else None
    selected=selected or next((b['id'] for b in batches if b['total']),None)
    return {'batches':batches,'active_batch_id':selected,'operations':operations,'work_active':bool(active),'profile_version':profile.get('version'),'documents':documents}

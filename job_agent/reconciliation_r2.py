"""Explicit restart-safe local reconciliation. Never touches employer browsers."""
import json
from .database import now
from .runtime_policy import digest
from .application_answers import approved_facts,answer
from .m3 import M3Engine


def reconcile(db):
    profile,facts,sources,_=approved_facts(db);engine=M3Engine(db)
    signature=digest([profile,facts])
    from .fact_memory import record
    with db.transaction() as conn:
        for key,value in facts.items():
            if conn.execute("SELECT 1 FROM fact_memory WHERE field_key=? AND scope='shared'",(key,)).fetchone():continue
            evidence=sources[key]['evidence']
            record(conn,key,value,source=json.dumps(evidence,sort_keys=True),version=profile.get('version'),priority=min(e['priority'] for e in evidence))
    result={'revised_packets':0,'preserved_manual_text':0,'browser_records':0,'unchanged':0,'conflicts':[k for k,v in sources.items() if v.get('resolution')=='CONFLICT'],'email_metadata_restored':restore_cached_headers(db),'identity_blockers':[]}
    with db.transaction() as conn:packets=[dict(r) for r in conn.execute('SELECT * FROM application_packets')]
    for p in packets:
        token=digest([p['packet_id'],signature])
        with db.transaction() as conn:
            if conn.execute('SELECT 1 FROM r2_reconciliations WHERE id=?',(token,)).fetchone():result['unchanged']+=1;continue
            old=dict(conn.execute('SELECT * FROM application_packet_versions WHERE packet_id=? AND version=?',(p['packet_id'],p['current_version'])).fetchone())
            identity=conn.execute('SELECT company,title FROM jobs WHERE id=?',(p['job_id'],)).fetchone()
        identity_verified=bool(identity['company'] and identity['title'])
        if not old['user_edited'] and identity_verified:engine.prepare(p['job_key'])
        if not identity_verified:result['identity_blockers'].append({'packet_id':p['packet_id'],'reason':'vacancy_identity_unverified_prior_text_retained'})
        with db.transaction() as conn:
            conn.execute('BEGIN IMMEDIATE')
            current=dict(conn.execute('SELECT * FROM application_packets WHERE packet_id=?',(p['packet_id'],)).fetchone())
            v=dict(conn.execute('SELECT * FROM application_packet_versions WHERE packet_id=? AND version=?',(p['packet_id'],current['current_version'])).fetchone())
            provenance=json.loads(v['provenance']);provenance['fact_reconciliation']={'version':'r2-1','signature':signature,'profile_version':profile.get('version'),'fact_sources':sources,'based_on_version':current['current_version'],'manual_text_preserved':bool(v['user_edited']),'vacancy_identity_verified':identity_verified,'prior_text_retained':not identity_verified}
            version=current['current_version']+1
            conn.execute('INSERT INTO application_packet_versions VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(p['packet_id'],version,v['subject'],v['email_html'],v['email_text'],v['supporting_statement'],v['fit_summary'],v['gaps'],json.dumps(provenance),v['generator'],v['user_edited'],now()))
            job=dict(conn.execute('SELECT * FROM jobs WHERE id=?',(p['job_id'],)).fetchone())
            missing=[]
            for label in json.loads(current['missing_information']):
                resolved,_=answer({'label':label,'type':'text','required':True},facts,profile,job['description'],job['title'] or '',job['company'] or '','india' in (job['location'] or '').casefold())
                if label not in facts and resolved is None:missing.append(label)
            if not identity_verified:missing.append('vacancy_identity_unverified')
            conn.execute('UPDATE application_packets SET current_version=?,profile_version=?,missing_information=?,updated_at=? WHERE packet_id=?',(version,profile.get('version'),json.dumps(missing),now(),p['packet_id']))
            questions=conn.execute('SELECT * FROM application_questions WHERE packet_id=?',(p['packet_id'],)).fetchall()
            for q in questions:
                latest=conn.execute('SELECT * FROM application_answers WHERE question_id=? ORDER BY version DESC LIMIT 1',(q['question_id'],)).fetchone()
                if latest and latest['status'] not in {'NEEDS_USER_INFORMATION','PROPOSED'}:continue
                value,key=answer({'label':q['question'],'type':'text','required':True,'max_length':q['character_limit'] or -1},facts,profile,job['description'],job['title'] or '',job['company'] or '','india' in (job['location'] or '').casefold())
                if value is None or latest and latest['answer']==value:continue
                import uuid
                conn.execute('INSERT INTO application_answers VALUES(?,?,?,?,?,?,?)',(uuid.uuid4().hex,q['question_id'],latest['version']+1 if latest else 1,value,'PROPOSED',json.dumps({'resolver':'canonical-facts-1','key':key,'sources':sources.get(key,{}) if isinstance(key,str) else key}),now()))
            conn.execute('INSERT INTO r2_reconciliations VALUES(?,?,?)',(token,json.dumps({'packet_id':p['packet_id'],'from_version':p['current_version'],'to_version':version,'profile_version':profile.get('version'),'manual_text_preserved':bool(v['user_edited'])}),now()))
        result['revised_packets']+=1;result['preserved_manual_text']+=bool(v['user_edited'])
    from .browser_store import BrowserStore
    from .review_workflow import resolution_report
    store=BrowserStore(db)
    for item in store.list(include_history=True):
        report=resolution_report(db,item['id']);inspection=json.loads(store.get(item['id'])['inspection'])
        if inspection.get('answer_resolution')==report:continue
        inspection['answer_resolution']=report
        values={'inspection':{'answer_resolution':report}}
        if report.get('fields') and not any(f['state']=='NEEDS_INSPECTION' for f in report['fields']):
            values['missing']=[f['label'] for f in report['fields'] if f['state'] in {'UNKNOWN','CONFLICT'}]
            if not values['missing'] and item['state']=='NEEDS_USER_ANSWER':values.update(state='NEEDS_EMPLOYER_CHECK',phase='Saved answers resolved; inspect current employer controls before filling')
        store.update(item['id'],**values);result['browser_records']+=1
    return result


def restore_cached_headers(db):
    """Read received-message headers already on disk. No mailbox or message-body access."""
    import hashlib
    restored=0
    with db.transaction() as conn:
        rows=conn.execute('SELECT message_id,received_at FROM gmail_intake WHERE message_id NOT IN (SELECT message_id FROM email_message_metadata)').fetchall()
        for row in rows:
            path=db.path.parent/'gmail'/'message-cache'/(hashlib.sha256(row['message_id'].encode()).hexdigest()+'.json')
            if not path.is_file() or path.stat().st_size>3*1024*1024:continue
            try:
                data=json.loads(path.read_text(encoding='utf-8'));headers={h.get('name','').casefold():h.get('value','') for h in data.get('payload',{}).get('headers',[])}
                if data.get('id')!=row['message_id'] or not headers.get('subject'):continue
                conn.execute('INSERT OR IGNORE INTO email_message_metadata VALUES(?,?,?,?)',(row['message_id'],str(headers.get('from',''))[:1000],str(headers['subject'])[:1000],row['received_at']));restored+=1
            except (ValueError,TypeError,AttributeError):continue
    return restored

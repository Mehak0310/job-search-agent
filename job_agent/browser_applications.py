r"""Persistent visible Chrome preparation. No automatic submission capability.

Run with .venv\Scripts\python.exe -m job_agent.browser_applications --limit 5.
Chrome is an independent process: disconnecting Playwright never closes it.
"""
import argparse
import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit
from .database import Database,now
from .browser_store import BrowserStore,ats_for
from .browser_forms import Dispatcher,NetworkBoundary,GUARD_JS,inventory,locate,public_url,ATS_HOSTS,selected_value
from .application_answers import approved_facts,answer,tailored
from .document_manifest import resolve_approved_document,sha256
from .runtime_policy import digest,issue_authorization,require_external_write
from .workflow_guard import workflow_lease

PORT=9224
CONNECT_URLS={'linkedin':'https://www.linkedin.com/login','naukri':'https://www.naukri.com/nlogin/login'}
USER_SCOPE='User authorized persistent visible-browser preparation and unchanged approved-document uploads; manual Submit only'


def root_for(db):return db.path.resolve().parent/'browser-applications'


def browser_metadata():
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(f'http://127.0.0.1:{PORT}/json/version',timeout=2) as response:
        return json.load(response)


def ensure_browser(db):
    root=root_for(db);root.mkdir(parents=True,exist_ok=True)
    marker=root/'session.json'
    try:
        metadata=browser_metadata()
        saved=json.loads(marker.read_text()) if marker.is_file() else {}
        if saved.get('websocket_id')!=metadata['webSocketDebuggerUrl'].split('/')[-1]:
            raise ValueError('browser_port_owned_by_another_session')
        return metadata
    except OSError:pass
    profile=root/'profile';profile.mkdir(exist_ok=True)
    chrome=Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
    if not chrome.is_file():raise ValueError('installed_chrome_not_found')
    flags=getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0)|getattr(subprocess,'DETACHED_PROCESS',0)
    # Dedicated profile only; ordinary browser security settings stay enabled.
    subprocess.Popen([str(chrome),'--user-data-dir='+str(profile),f'--remote-debugging-port={PORT}',
        '--remote-debugging-address=127.0.0.1','--no-first-run','--restore-last-session','about:blank'],
        stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=flags)
    for _ in range(30):
        try:
            metadata=browser_metadata();break
        except OSError:time.sleep(.2)
    else:raise ValueError('browser_start_timeout')
    marker.write_text(json.dumps({'websocket_id':metadata['webSocketDebuggerUrl'].split('/')[-1],
        'profile_directory':'profile','started_at':now()}),encoding='utf-8')
    return metadata


def target_id(page):
    session=page.context.new_cdp_session(page)
    try:return session.send('Target.getTargetInfo')['targetInfo']['targetId']
    finally:session.detach()


def find_page(browser,identifier):
    for context in browser.contexts:
        for page in context.pages:
            if target_id(page)==identifier:return page
    return None


def run_read(store,application_id,kind,payload,operation):
    """One retry owner, persisted before attempts. Only transient navigation errors."""
    from playwright.sync_api import TimeoutError as BrowserTimeout,Error as BrowserError
    for retry in range(3):
        identifier,execute=store.begin_operation(application_id,kind,payload)
        if not execute:return None
        try:
            result=operation();store.end_operation(identifier,'SUCCEEDED');return result
        except (BrowserTimeout,BrowserError) as error:
            transient=isinstance(error,BrowserTimeout) or any(code in str(error) for code in ('ERR_CONNECTION_RESET','ERR_TIMED_OUT','ERR_CONNECTION_CLOSED'))
            store.end_operation(identifier,'FAILED' if transient else 'BLOCKED',type(error).__name__)
            if not transient or retry==2:raise
            time.sleep(2**retry+random.uniform(0,.2))


def form_frame(page):
    frames=[]
    for iframe in page.locator('iframe').all():
        source=iframe.get_attribute('src') or ''
        if urlsplit(source).hostname in ATS_HOSTS:
            iframe.scroll_into_view_if_needed(timeout=3000)
    # CDP reattachment to cross-origin ATS frames is asynchronous. Wait for the
    # specific supported frame's controls; never substitute a generic input.
    for attempt in range(20):
        frames=[]
        for frame in page.frames:
            host=urlsplit(frame.url).hostname
            if frame==page.main_frame or host in ATS_HOSTS:
                fields=inventory(frame)
                usable=[f for f in fields if f['type'] not in {'hidden','submit','button'} and f.get('label')]
                if usable:frames.append((frame,fields))
        if frames:break
        page.wait_for_timeout(250)
    if len(frames)>1:
        with_files=[pair for pair in frames if any(f['type']=='file' for f in pair[1])]
        if len(with_files)==1:return with_files[0]
        raise ValueError('ambiguous_application_frames')
    if not frames:raise ValueError('supported_form_not_found')
    return frames[0]


def upload_acceptance(frame,field,name,responses):
    try:control=locate(frame,field)
    except ValueError:control=None
    selected=control.evaluate('(e)=>[...e.files].map(f=>f.name)') if control is not None else []
    group=control.evaluate('(e)=>(e.closest(".application-question,.resume-upload,.field")||e.parentElement).innerText') if control is not None else ''
    visible=name.casefold() in frame.locator('body').inner_text().casefold()
    if control is None and visible:
        group=' '.join(frame.get_by_text(name,exact=False).all_text_contents())
    accepted_ui=visible or (name in selected and bool(re.search(r'\bsuccess\b|uploaded|attached',group,re.I)))
    error=bool(re.search(r'failed|\berror\b|could not|cannot read',group,re.I))
    return {'filename_visible':visible,'selected_filename_verified':name in selected,'acceptance_visible':accepted_ui,
            'error_visible':error,'staging_responses':responses,
            'verified':accepted_ui and not error and bool(responses) and all(200<=r['status']<300 for r in responses)}


def surname_fill(dispatch,field,value,facts):
    variants=json.loads(facts.get('surname_fallbacks','[]')) if re.search(r'last name|surname|family name',field['label'],re.I) else []
    for candidate in variants or [value]:
        result=dispatch.act('FILL',field,candidate)
        control=locate(dispatch.frame,field)
        control.evaluate('(e)=>e.blur()')
        dispatch.frame.wait_for_timeout(150)
        invalid=control.evaluate("e=>e.getAttribute('aria-invalid')==='true'||(e.validity&&!e.validity.valid)")
        if not invalid:return result
    raise ValueError('surname_variants_rejected_by_visible_validation')


def recover_page(browser,item):
    original=urlsplit(item['url']);identifier=re.search(r'(?:jobs/|gh_jid=)(\d+)',original.path+'?'+original.query)
    def matches(candidate):
        current=urlsplit(candidate.url)
        if current.hostname!=original.hostname:return False
        if identifier:return bool(re.search(r'(?:jobs/|gh_jid=)'+identifier.group(1)+r'(?:\D|$)',current.path+'?'+current.query))
        return current.path.rstrip('/').removesuffix('/apply')==original.path.rstrip('/').removesuffix('/apply') and current.query==original.query
    page=find_page(browser,item['target_id']) if item.get('target_id') else None
    if page and matches(page):return page
    candidates=[page for context in browser.contexts for page in context.pages if matches(page)]
    return candidates[0] if len(candidates)==1 else None


def prepare_one(store,application,browser,metadata,allow_upload=True):
    db=store.db;job=store.job(application['job_id'],require_verified=True);root=root_for(db)
    if application['target_id']:
        page=recover_page(browser,application)
        if page is None:
            store.update(application['id'],state='SESSION_LOST',missing=['Saved tab/session is unavailable. Review existing employer progress and duplicate history before explicit reconstruction.'])
            return
        store.update(application['id'],target_id=target_id(page),session_id=metadata['webSocketDebuggerUrl'].split('/')[-1])
        # Existing prepared tabs are never refilled or overwritten on restart.
        if application.get('preparation_state',application['state'])!='PREPARING':page.bring_to_front();return
    public_url(application['url'])
    context=browser.contexts[0]
    if not application['target_id']:page=context.new_page()
    boundary=NetworkBoundary(urlsplit(application['url']).hostname)
    page.route('**/*',boundary.route);page.on('response',boundary.response)
    def cancel_download(download):download.cancel()
    page.on('download',cancel_download)
    store.update(application['id'],target_id=target_id(page),session_id=metadata['webSocketDebuggerUrl'].split('/')[-1])
    previous_path=root/(application['id']+'.json')
    previous_actions=json.loads(previous_path.read_text(encoding='utf-8')).get('actions',[]) if previous_path.is_file() else []
    missing=[];uploads=json.loads(application['documents']);checks=json.loads(job['missing_facts'] or '[]');inspection={};private_fields=[]
    try:
        response=None
        if not application['target_id']:
            response=run_read(store,application['id'],'navigation',[application['url'],target_id(page)],
                              lambda:page.goto(application['url'],wait_until='domcontentloaded',timeout=30000))
        if response is not None and response.status>=400:raise ValueError('vacancy_http_'+str(response.status))
        try:page.wait_for_load_state('networkidle',timeout=15000)
        except Exception:pass # bounded hydration wait; inventory still verifies actual controls
        body=page.locator('body').inner_text(timeout=10000)
        if re.search(r'job (?:is no longer|has been closed)|no longer accepting applications|position has been filled|job not found',body,re.I):
            raise ValueError('vacancy_closed')
        if any(f.is_visible() for f in page.locator('input[type=password]').all()):
            store.update(application['id'],state='NEEDS_LOGIN',session_health='LOGIN_REQUIRED',inspection={'error_code':'authentication_required'},missing=['Complete employer login and MFA yourself in this browser tab.']);return
        if re.search(r'captcha|verify you are human',body,re.I):
            store.update(application['id'],state='NEEDS_LOGIN',missing=['Human verification shown; complete it yourself, then explicitly re-inspect.']);return
        try:frame,fields=form_frame(page)
        except ValueError:
            # Follow only a demonstrated direct application anchor, never a button
            # named Submit or an assumed ATS path.
            links=page.locator('a[href]').evaluate_all("els=>els.map(e=>({text:e.innerText.trim(),url:e.href}))")
            candidates=[link for link in links if re.fullmatch(r'Apply(?: for (?:this )?(?:job|role))?(?: now)?',link['text'],re.I)
                        and urlsplit(link['url']).hostname in ATS_HOSTS]
            if len(candidates)!=1:raise ValueError('supported_application_entry_not_found')
            public_url(candidates[0]['url']);run_read(store,application['id'],'application_navigation',candidates[0]['url'],lambda:page.goto(candidates[0]['url'],wait_until='networkidle',timeout=30000))
            frame,fields=form_frame(page)
        frame.evaluate(GUARD_JS)
        if ats_for(frame.url)=='ashby':
            checks.append('Ashby control coverage is experimental; only uniquely identified standard fields are supported.')
        # Full stored JD is retained when an apply-only route omits its description.
        jd=job['description'];live_jd=body.split('Apply for this job')[0]
        if job['title'].casefold() not in body.casefold():checks.append('Live title requires agent comparison; no activity upgrade inferred from generic form.')
        if len(live_jd)>500 and re.search(r'responsibilit|qualification|what you|requirements',live_jd,re.I):jd=live_jd
        if len(jd)<300:checks.append('Full vacancy description remains insufficient for tailored answers.')
        profile,facts,sources,manifest=approved_facts(db)
        india=job['india_state']=='PASS' or 'india' in job['location'].casefold()
        if not india:checks.append('India eligibility must be explicit before work-authorization/sponsorship answers are mapped.')
        dispatch=Dispatcher(frame);grants=db.path.parent/'action-authorizations'
        # Refresh after each action; conditional questions and option lists can change.
        seen=set()
        for _ in range(100):
            fields=inventory(frame)
            candidates=[f for f in fields if (f.get('id') or f.get('name') or f.get('label')) and f['type'] not in {'hidden','submit','button','file'}
                        and f['visible'] and not f['disabled'] and digest([f['id'],f['name'],f['label'],f['type']]) not in seen]
            if not candidates:break
            field=candidates[0];identifier=digest([field['id'],field['name'],field['label'],field['type']]);seen.add(identifier)
            if field['type']=='radio':
                group=[f for f in fields if f['type']=='radio' and f['name']==field['name'] and f['group']==field['group']]
                for option in group:seen.add(digest([option['id'],option['name'],option['label'],option['type']]))
                if any(option['value'] for option in group):continue
                question={**field,'label':field['group'] or field['label'],'type':'text'}
                value,source=answer(question,facts,profile,jd,job['title'],job['company'],india)
                if re.search(r'notice|joining|join.*(?:soon|time)',question['label'],re.I) and '90' in facts.get('notice_period',''):
                    exact=[option for option in group if re.fullmatch(r'More than 60\s*Days',option['label'].strip(),re.I)]
                    if len(exact)==1:value=exact[0]['label'];source='notice_period'
                match=[option for option in group if value is not None and option['label'].strip().casefold()==value.casefold()]
                if len(match)!=1:
                    if field['required']:missing.append(question['label'])
                    continue
                field=match[0]
            if field['type']!='radio':value,source=answer(field,facts,profile,jd,job['title'],job['company'],india)
            if field['value'] not in ('',None,False,[]):
                prior=next((p for p in previous_actions if p.get('field',{}).get('id')==field['id'] and p.get('outcome')=='verified' and p.get('readback')==field['value']),None)
                same_phone=source=='phone' and re.sub(r'\D','',str(field['value']))==re.sub(r'\D','',facts.get('phone',''))
                if value is None or value==field['value'] or not (prior or same_phone):
                    private_fields.append({'field':field,'outcome':'preserved_existing'});continue
            if value is None:
                if field['required']:missing.append(field['label'] or field['name'] or field['id'])
                private_fields.append({'field':field,'outcome':'unresolved' if field['required'] else 'optional_unanswered'});continue
            payload=digest([field['id'],field['name'],field['label'],value,'control-v4-exact-agreement']);snapshot=digest([job['packet_id'],job['current_version'],digest(jd),profile.get('version'),sources])
            grant=issue_authorization(grants,operation='portal_fill',target=application['url'],snapshot_hash=snapshot,payload_hash=payload,user_reference=USER_SCOPE)
            require_external_write('portal_fill',root=grants,authorization_id=grant,target=application['url'],snapshot_hash=snapshot,payload_hash=payload,consume=True)
            opid,perform=store.begin_operation(application['id'],'fill:'+identifier,payload)
            if not perform:
                # A restored/reset form can lose a previously verified value.
                # Reconcile only an actually empty control; original uploads are never replayed.
                if field['value'] in ('',None,False,[]):
                    store.end_operation(opid,'FAILED','live_field_empty_after_success')
                    opid,perform=store.begin_operation(application['id'],'fill:'+identifier,payload)
                else:continue
            try:
                action='SELECT' if field['tag']=='select' or field['role']=='combobox' or field['type']=='radio' else 'FILL'
                readback=surname_fill(dispatch,field,value,facts) if action=='FILL' else dispatch.act(action,field,value)
                store.end_operation(opid,'SUCCEEDED')
                store.update(application['id'],inspection={'stage':'Filling saved answers','answered':1+sum(p['outcome']=='verified' or p['outcome']=='preserved_existing' and p['field']['value'] not in ('',None,False,[]) for p in private_fields),'field_count':len(fields),'verified_at':now()})
                private_fields.append({'field':field,'answer':value,'readback':readback,'provenance':sources.get(source,source) if isinstance(source,str) else source,'outcome':'verified'})
            except Exception as error:
                store.end_operation(opid,'BLOCKED',type(error).__name__)
                if field['required']:missing.append(f"{field['label']}: supported control/option needs review")
                private_fields.append({'field':field,'outcome':'blocked','error_class':type(error).__name__})
        # Documents are uploaded only from the manifest, never generated or edited.
        for field in [f for f in inventory(frame) if f['type']=='file']:
            label=(field['label']+' '+field['id']+' '+field['name']).casefold()
            from .private_config import document_for_role
            role='resume' if 'resume' in label or 'cv' in label else 'cover_letter' if 'cover' in label and field['required'] else None
            if not role:continue
            item=document_for_role(manifest['documents'],role,db.path.parent)
            if not item:
                missing.append(role+': no unambiguous approved manifest reference');continue
            document_name=item['canonical_name']
            previous=next((d for d in json.loads(application['documents']) if d['name']==document_name and d.get('verified')),None)
            if previous:
                current=upload_acceptance(frame,field,document_name,previous.get('staging_responses',[]))
                uploads=[d for d in uploads if d['name']!=document_name]+[{**previous,**current}]
                if not current['verified']:missing.append(document_name+': existing upload state requires reconciliation')
                continue
            if not allow_upload:
                missing.append(document_name+': upload reserved for user');continue
            item=next((item for item in manifest['documents'] if item.get('canonical_name')==document_name),None)
            if not item:
                missing.append(document_name+': no approved manifest reference');continue
            opid=None;start=None
            try:
                path=resolve_approved_document(item,db.path.parent);file_hash=sha256(path)
                payload=digest([document_name,file_hash]);opid,perform=store.begin_operation(application['id'],'upload:'+field['id']+field['name'],payload,write=True)
                if not perform:
                    missing.append(document_name+': prior successful staging must be reconciled against current form');continue
                grant=issue_authorization(grants,operation='portal_upload',target=application['url'],snapshot_hash=digest([job['id'],job['current_version'],file_hash]),payload_hash=payload,user_reference=USER_SCOPE)
                require_external_write('portal_upload',root=grants,authorization_id=grant,target=application['url'],payload_hash=payload,consume=True)
                boundary.upload=True;start=len(boundary.upload_responses)
                dispatch.act('UPLOAD',field,{'name':document_name,'mimeType':'application/pdf','buffer':path.read_bytes()})
                # Acceptance requires visible filename and an actual staging response.
                deadline=time.monotonic()+15;visible=False
                while time.monotonic()<deadline:
                    visible=document_name in frame.locator('body').inner_text()
                    if visible and len(boundary.upload_responses)>start:break
                    page.wait_for_timeout(300)
                responses=boundary.upload_responses[start:]
                verification=upload_acceptance(frame,field,document_name,responses)
                accepted=verification['verified']
                uploads=[d for d in uploads if d['name']!=document_name]+[{'name':document_name,'sha256':file_hash,**verification}]
                store.end_operation(opid,'SUCCEEDED' if accepted else 'UNCERTAIN',None if accepted else 'upload_acceptance_not_verified')
                if not accepted:missing.append(document_name+': upload acceptance not verified; reconcile, do not blindly retry')
            except Exception as error:
                responses=boundary.upload_responses[start:] if start is not None else []
                uploads=[d for d in uploads if d['name']!=document_name]+[{'name':document_name,'sha256':item.get('sha256'),'verified':False,'error_code':type(error).__name__,'staging_responses':responses}]
                if opid is not None:store.end_operation(opid,'UNCERTAIN',type(error).__name__)
                missing.append(document_name+': '+str(error) if isinstance(error,ValueError) else document_name+': upload needs review')
            finally:boundary.upload=False
        # Re-inventory validates current required/conditional controls after uploads.
        final_fields=inventory(frame)
        for field in final_fields:
            if field['type']=='radio':
                if not any(f['type']=='radio' and f['name']==field['name'] and f['value'] for f in final_fields):
                    if field['required']:missing.append(field['group'] or field['label'])
                continue
            if field['required'] and field['type'] not in {'hidden','submit','button','file'} and field['visible'] and field['value'] in ('',None,False,[]):
                # Custom selects keep an empty search input after selection; use recorded readback.
                if not any(p.get('outcome')=='verified' and p['field']['id']==field['id'] for p in private_fields):missing.append(field['label'] or field['name'] or field['id'])
        statement,inputs=tailored(profile,jd,job['title'],job['company'])
        inspection={'verified_at':now(),'field_count':len(final_fields),'answered':sum(p['outcome']=='verified' or p['outcome']=='preserved_existing' and p['field']['value'] not in ('',None,False,[]) for p in private_fields),'ats':application['ats'],'jd_sha256':digest(jd),
                    'blocked_network_writes':boundary.blocked,'answer_generation':inputs,
                    'upload_note':'Filling and document staging can transmit data/autosave. Submission remains a separate manual action.'}
        private={'inventory':final_fields,'actions':private_fields,'full_jd':jd,'supporting_statement':statement,'inspection':inspection}
        (root/(application['id']+'.json')).write_text(json.dumps(private,indent=2),encoding='utf-8')
        page.screenshot(path=str(root/(application['id']+'.png')),full_page=True)
        state='NEEDS_USER_ANSWER' if missing else 'NEEDS_EMPLOYER_CHECK' if checks else 'READY_FOR_USER_REVIEW'
        store.update(application['id'],state=state,inspection=inspection,missing=sorted(set(missing)),checks=checks,documents=uploads)
        page.bring_to_front()
    except Exception as error:
        code=str(error) if isinstance(error,ValueError) else type(error).__name__
        if code in {'vacancy_http_404','vacancy_http_410','vacancy_closed'}:
            with db.transaction() as conn:conn.execute("UPDATE jobs SET activity_status='CLOSED' WHERE id=?",(job['id'],))
        state='NEEDS_LOGIN' if 'login' in code or 'authentication' in code else 'ERROR'
        store.update(application['id'],state=state,missing=['Agent action: '+code],inspection={'error_code':code,'verified_at':now()},documents=uploads,checks=checks)
    finally:
        # Automation ends; release interception so the USER can review and submit.
        # No further form controls are driven by this worker after this point.
        for frame in page.frames:
            try:frame.evaluate('window.__jobPreparationActive=false')
            except Exception:pass
        page.unroute('**/*',boundary.route);page.remove_listener('response',boundary.response)
        page.remove_listener('download',cancel_download)


@contextmanager
def browser_connection():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:yield p.chromium.connect_over_cdp(f'http://127.0.0.1:{PORT}',timeout=10000)


def probe_employer_login(browser,item):
    page=recover_page(browser,item)
    if page is None:return 'LOST'
    if re.search(r'captcha|verify you are human',page.locator('body').inner_text(timeout=5000),re.I):return 'HUMAN_ONLY'
    if any(f.is_visible() for f in page.locator('input[type=password]').all()):return 'WAITING'
    fields=inventory(page.main_frame)
    labels=' '.join(f['label'] for f in fields if f['visible'] and not f['disabled']).casefold()
    return 'VERIFIED' if ats_for(page.url) and re.search(r'(?:first|full|legal) name',labels) and 'email' in labels else 'WAITING'


def wait_for_employer_logins(db,batch_id,workers,workflow_id,owner,metadata,allow_upload):
    from .orchestration import login_tick
    store=BrowserStore(db);store.worker_guard=lambda:workers.assert_owner(workflow_id,owner)
    while True:
        with db.transaction() as c:waiting=[r['application_id'] for r in c.execute("SELECT application_id FROM employer_login_waits WHERE batch_id=? AND state='WAITING'",(batch_id,))]
        if not waiting:return
        for identifier in waiting:
            workers.assert_owner(workflow_id,owner)
            if login_tick(db,identifier)!='WAITING':continue
            item=store.get(identifier)
            try:
                with browser_connection() as browser:
                    observed=probe_employer_login(browser,item)
                    if observed=='LOST':store.update(identifier,state='SESSION_LOST');login_tick(db,identifier);continue
                    if observed=='HUMAN_ONLY':
                        with db.transaction() as c:c.execute("UPDATE employer_login_waits SET state='HUMAN_ONLY' WHERE application_id=?",(identifier,))
                        continue
                    if login_tick(db,identifier,authenticated=observed=='VERIFIED')=='VERIFIED':
                        store.job(item['job_id'],require_verified=True)
                        store.update(identifier,state='PREPARING')
                        prepare_one(store,store.get(identifier),browser,metadata,allow_upload)
            except Exception:
                with db.transaction() as c:c.execute("UPDATE employer_login_waits SET state='ERROR',error='inspection_requires_review' WHERE application_id=?",(identifier,))
        workers.checkpoint(workflow_id,owner,len(BrowserStore(db).list(batch_id)),'Waiting for employer login; other application tabs remain reviewable')
        # Only the coordinator waits; both page-actor slots are free. The
        # existing heartbeat thread remains live; no credentials are entered.
        time.sleep(1)


def execute_batch(db,batch_id,allow_upload=True,only_application=None,workflow_id=None,_connection=None,_prepare=None):
    from .browser_workers import BrowserWorkers
    store=BrowserStore(db);root=root_for(db)
    items=[r for r in store.list(batch_id) if not only_application or r['id']==only_application]
    with db.transaction() as conn:positions={r['job_id']:r['reserved_order'] for r in conn.execute('SELECT job_id,reserved_order FROM application_priority WHERE batch_id=?',(batch_id,))}
    if positions:items.sort(key=lambda r:(positions.get(r['job_id']) or 999999,r['job_id']))
    workers=BrowserWorkers(db);workflow_id=workflow_id or workers.enqueue('PREPARE',[r['id'] for r in items],batch_id)
    with workers.running(workflow_id) as owner:
        store.worker_guard=lambda:workers.assert_owner(workflow_id,owner)
        with workflow_lease(root/'controller'):
            metadata=ensure_browser(db)
            with db.transaction() as conn:conn.execute("UPDATE browser_batches SET status='RUNNING' WHERE id=?",(batch_id,))
            from concurrent.futures import ThreadPoolExecutor,as_completed
            def prepare_item(item):
                local=BrowserStore(db);local.worker_guard=lambda:workers.assert_owner(workflow_id,owner)
                if local.get(item['id'])['application_outcome']!='NOT_SUBMITTED':return
                try:
                    with (_connection or browser_connection)() as browser:
                        (_prepare or prepare_one)(local,local.get(item['id']),browser,metadata,allow_upload)
                except Exception as error:
                    if str(error)=='worker_ownership_lost':raise
                    if str(error)=='unknown_eligibility_requires_verification':local.update(item['id'],state='NEEDS_EMPLOYER_CHECK',missing=[],checks=['Eligibility changed or is UNKNOWN; verification required before any preparation.'])
                    else:local.update(item['id'],state='ERROR',missing=['Agent action: '+type(error).__name__],retry_condition='Inspect the recorded failure before retrying; no submission was inferred.')
            # One session coordinator; each actor owns its connection and tab.
            # No synchronous Playwright object crosses a thread boundary.
            with ThreadPoolExecutor(max_workers=2,thread_name_prefix='application-tab') as pool:
                futures=[]
                for item in items:
                    with db.transaction() as conn:workers.event(conn,workflow_id,'PRIORITY_SELECTED',{'job_id':item['job_id'],'position':positions.get(item['job_id']),'policy':'verified-priority-1'})
                    futures.append(pool.submit(prepare_item,item))
                for completed,future in enumerate(as_completed(futures),1):
                    future.result();workers.checkpoint(workflow_id,owner,completed,'Inspected application '+str(completed)+' of '+str(len(items)))
            wait_for_employer_logins(db,batch_id,workers,workflow_id,owner,metadata,allow_upload)
            with db.transaction() as conn:conn.execute("UPDATE application_priority SET state='PROCESSED',last_processed=?,updated_at=? WHERE batch_id=? AND state='RESERVED'",(now(),now(),batch_id))
            with db.transaction() as conn:conn.execute("UPDATE browser_batches SET status='REVIEW',finished_at=? WHERE id=?",(now(),batch_id))
    return store.list(batch_id)


def run_worker_batch(db,batch_id,allow_upload=True,only_application=None,workflow_id=None):
    try:return execute_batch(db,batch_id,allow_upload,only_application,workflow_id)
    except Exception as error:
        # A failed controller/launch must not leave the dashboard waiting forever.
        code=str(error) if isinstance(error,ValueError) and str(error) in {'workflow_already_running','browser_start_timeout','browser_port_owned_by_another_session'} else type(error).__name__
        store=BrowserStore(db)
        with db.transaction() as conn:conn.execute("UPDATE browser_batches SET status='ERROR',finished_at=?,error_code=? WHERE id=?",(now(),code,batch_id))
        for row in store.list(batch_id):
            if row['state']=='PREPARING' and (not only_application or row['id']==only_application):store.update(row['id'],state='ERROR',inspection={'error_code':code,'verified_at':now()},missing=['Agent action: interrupted preparation requires reconciliation; no submission was inferred.'])
        return {'state':'ERROR','error_code':code}


def launch_worker(db,batch_id,allow_upload=True,only_application=None):
    from .browser_workers import BrowserWorkers
    workers=BrowserWorkers(db);ids=[r['id'] for r in BrowserStore(db).list(batch_id) if not only_application or r['id']==only_application]
    workflow_id=workers.enqueue('PREPARE',ids,batch_id)
    root=root_for(db);root.mkdir(parents=True,exist_ok=True)
    args=[sys.executable,'-m','job_agent.browser_applications','--db',str(db.path.resolve()),'--worker',batch_id]
    if not allow_upload:args.append('--no-upload')
    if only_application:args+=['--only-application',only_application]
    args+=['--workflow',workflow_id]
    with (root/'worker.log').open('ab') as log:
        try:process=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except OSError:
            workers.finish(workflow_id,'ERROR','worker_launch_failed');raise ValueError('worker_launch_failed') from None
    workers.attach_pid(workflow_id,process.pid)
    return process.pid


def switch_tab(db,application_id):
    from playwright.sync_api import sync_playwright
    store=BrowserStore(db);item=store.get(application_id)
    with workflow_lease(root_for(db)/'controller'):
        try:metadata=browser_metadata()
        except OSError:
            store.update(application_id,state='SESSION_LOST');return {'state':'SESSION_LOST'}
        with sync_playwright() as p:
            browser=p.chromium.connect_over_cdp(f'http://127.0.0.1:{PORT}')
            page=recover_page(browser,item)
            if not page:
                store.update(application_id,state='SESSION_LOST');return {'state':'SESSION_LOST'}
            page.bring_to_front();return {'state':item['state']}


def reinspect(db,application_id):
    """Read-only reconciliation, including actual user submission confirmations."""
    from playwright.sync_api import sync_playwright
    store=BrowserStore(db);item=store.get(application_id)
    with workflow_lease(root_for(db)/'controller'):
        try:metadata=browser_metadata()
        except OSError:
            store.update(application_id,state='SESSION_LOST');return store.list()
        with sync_playwright() as p:
            browser=p.chromium.connect_over_cdp(f'http://127.0.0.1:{PORT}')
            page=recover_page(browser,item)
            if not page:
                store.update(application_id,state='SESSION_LOST');return store.list()
            store.update(application_id,target_id=target_id(page),session_id=metadata['webSocketDebuggerUrl'].split('/')[-1])
            text=page.locator('body').inner_text()
            if re.search(r'verify (?:that )?you are human|complete (?:the )?captcha|human verification required',text,re.I):
                store.update(application_id,state='NEEDS_LOGIN',session_health='LOGIN_REQUIRED',retry_condition='Complete the visible challenge yourself; automation will not retry it.')
                return store.list()
            # Only a bound existing tab with an actual supported confirmation can
            # upgrade evidence. A closed tab or manually reported status cannot.
            confirmation=page.locator('#application_confirmation,[data-qa="application-confirmation"],.application-confirmation')
            if confirmation.count()==1 and confirmation.first.is_visible() and re.search(r'application (?:has been |was )?(?:successfully )?submitted|thank you for applying',confirmation.first.inner_text(),re.I):
                evidence_path=root_for(db)/(application_id+'-confirmation.png')
                page.screenshot(path=str(evidence_path),full_page=True)
                reference='browser-confirmation:'+sha256(evidence_path)
                store.update(application_id,state='SUBMISSION_CONFIRMED',confirmation_ref=reference,
                    inspection={'verified_at':now(),'ats':item['ats'],'confirmation_evidence':reference})
                return store.list()
            try:frame,fields=form_frame(page)
            except ValueError:
                if item['state']=='USER_REPORTED_SUBMITTED':
                    store.update(application_id,inspection={'verified_at':now(),'error_code':'No supported confirmation marker; retained user report only'})
                else:store.update(application_id,state='SESSION_LOST',missing=['ATS form/frame is unavailable in the saved tab; inspect existing employer progress before reconstruction.'])
                return store.list()
            documents=json.loads(item['documents']);missing=[]
            for field in fields:
                if not field['required'] or not field['visible'] or field['type'] in {'hidden','submit','button','file'}:continue
                if field['type']=='radio':
                    if not any(f['type']=='radio' and f['name']==field['name'] and f['value'] for f in fields):missing.append(field['group'] or field['label'])
                    continue
                value=field['value']
                if field.get('role')=='combobox':
                    value=selected_value(locate(frame,field))
                    if field['id']=='country' and not value:value=locate(frame,field).evaluate('(e)=>e.parentElement.parentElement.innerText.trim()')
                if value in ('',None,False,[]):missing.append(field['label'] or field['group'] or 'Unidentified required control; agent inspection needed')
            for document in documents:
                from .private_config import document_role
                manifest_path=db.path.parent/'documents'/'manifest.json'
                role_entries=json.loads(manifest_path.read_text(encoding='utf-8')).get('documents',[]) if manifest_path.is_file() else []
                role_entry=next((d for d in role_entries if d.get('canonical_name')==document['name']),{'canonical_name':document['name']})
                field=next((f for f in fields if f['type']=='file' and ('resume' in (f['id']+f['name']).casefold() if document_role(role_entry,db.path.parent)=='resume' else 'cover' in (f['id']+f['name']).casefold())),None)
                if not field:
                    # Earlier Greenhouse input-detachment defect happened after
                    # successful staging. Reconcile from a matching durable
                    # byte-hash intent plus its visible accepted-file component.
                    _,_,_,manifest=approved_facts(db)
                    entry=next((d for d in manifest['documents'] if d['canonical_name']==document['name']),None)
                    file_hash=entry.get('sha256') if entry else None
                    with db.transaction() as conn:
                        operations=conn.execute("SELECT id,kind FROM browser_operations WHERE application_id=? AND kind LIKE 'upload:%'",(application_id,)).fetchall()
                    matched=[op for op in operations if op['id']==digest([application_id,op['kind'],digest([document['name'],file_hash])])]
                    visible=document['name'].casefold() in frame.locator('body').inner_text().casefold()
                    removable=frame.get_by_role('button',name=re.compile('remove',re.I)).count()>0
                    if matched and visible and removable:
                        document.update(verified=True,sha256=file_hash,filename_visible=True,acceptance_visible=True,
                                        verification_scope='matching original-byte intent and actual accepted-file/remove UI; HTTP response not retained')
                        for op in matched:store.end_operation(op['id'],'SUCCEEDED')
                    else:missing.append(document['name']+': current accepted-file component not verified')
                    continue
                verification=upload_acceptance(frame,field,document['name'],document.get('staging_responses',[]))
                if verification['verified']:
                    # Verify current browser-held bytes, not just a reused filename.
                    actual=locate(frame,field).evaluate('''async e=>{if(!e.files.length)return null;let b=await e.files[0].arrayBuffer();let h=await crypto.subtle.digest('SHA-256',b);return [...new Uint8Array(h)].map(x=>x.toString(16).padStart(2,'0')).join('');}''')
                    if actual!=document['sha256']:verification['verified']=False
                document.update(verification)
                if document['verified']:
                    missing=[m for m in missing if not m.startswith(document['name']+':')]
                    with db.transaction() as conn:
                        conn.execute("UPDATE browser_operations SET state='SUCCEEDED',error_code=NULL,next_action=NULL,updated_at=? WHERE application_id=? AND kind LIKE 'upload:%' AND state='UNCERTAIN'",(now(),application_id))
                else:missing.append(document['name']+': staging acceptance needs reconciliation')
            inspection=json.loads(item['inspection']);inspection.update(verified_at=now(),field_count=len(fields))
            checks=next((r['checks'] for r in store.list(include_history=True) if r['id']==application_id),json.loads(item['checks']));state=item['state']
            if item['application_outcome']=='NOT_SUBMITTED':
                try:checks=sorted(set(checks+json.loads(store.job(item['job_id'])['missing_facts'] or '[]')))
                except ValueError as error:
                    store.update(application_id,state='ERROR',inspection=inspection,documents=documents,missing=[],checks=['Saved eligibility blocks preparation: '+str(error)])
                    return store.list()
            if state not in {'USER_REPORTED_SUBMITTED','SUBMISSION_CONFIRMED'}:state='NEEDS_USER_ANSWER' if missing else 'NEEDS_EMPLOYER_CHECK' if checks else 'READY_FOR_USER_REVIEW'
            store.update(application_id,state=state,inspection=inspection,documents=documents,missing=sorted(set(missing)),checks=checks)
    return store.list()


def synchronize(db,application_id=None,workflow_id=None):
    from .browser_workers import BrowserWorkers,fair_applications
    workers=BrowserWorkers(db)
    rows=fair_applications(db,application_id)
    workflow_id=workflow_id or workers.enqueue('SYNC',[r['id'] for r in rows])
    with workers.running(workflow_id) as owner:
        return _synchronize_owned(db,workers,workflow_id,owner)


def _synchronize_owned(db,workers,workflow_id,owner):
    store=BrowserStore(db)
    try:ensure_browser(db)
    except (ValueError,OSError):
        workers.finish(workflow_id,'ERROR','browser_recovery_required',owner);return {'state':'AGENT_RECOVERY_REQUIRED'}
    identifiers=workers.get(workflow_id)['application_ids']
    for index,identifier in enumerate(identifiers):
        workers.checkpoint(workflow_id,owner,index,'Reconciling existing application '+str(index+1))
        item=store.get(identifier);item['inspection']=json.loads(item['inspection'])
        store.update(identifier,last_sync_at=now())
        if item['state']=='PREPARING':continue
        code=item.get('inspection',{}).get('error_code','')
        if code in {'vacancy_http_404','vacancy_http_410','vacancy_closed'}:
            with db.transaction() as conn:conn.execute("UPDATE jobs SET activity_status='CLOSED' WHERE id=?",(item['job_id'],))
            continue
        try:
            reinspect(db,item['id'])
            current=store.get(item['id'])
            saved_path=root_for(db)/(item['id']+'.json')
            saved=json.loads(saved_path.read_text(encoding='utf-8')) if saved_path.is_file() else {}
            profile,_,_,_=approved_facts(db)
            version=saved.get('inspection',{}).get('answer_generation',{}).get('profile_version')
            if current['state'] in {'NEEDS_USER_ANSWER','NEEDS_EMPLOYER_CHECK','READY_FOR_USER_REVIEW'} and version!=profile.get('version'):
                store.job(current['job_id'],require_verified=True)
                store.update(item['id'],state='PREPARING')
                # Existing form only, fenced by this sync owner. Never replay uploads.
                with workflow_lease(root_for(db)/'controller'):
                    with browser_connection() as browser:
                        store.worker_guard=lambda:workers.assert_owner(workflow_id,owner)
                        prepare_one(store,store.get(item['id']),browser,browser_metadata(),False)
        except ValueError as error:
            if str(error) in {'workflow_already_running','worker_ownership_lost'}:raise
            if str(error)=='unknown_eligibility_requires_verification':
                store.update(item['id'],state='NEEDS_EMPLOYER_CHECK',missing=[],checks=['Eligibility UNKNOWN; verification required before filling.'])
            elif str(error) in {'incompatible_known_office_location','incompatible_known_remote_country_scope','confirmed_failed_eligibility_check','confirmed_failed_mandatory_requirements','incompatible_or_already_applied','removed_from_active_review','existing_submission_history'}:
                store.update(item['id'],state='ERROR',missing=[],checks=['Preparation is blocked by saved eligibility rules; agent review required.'],inspection={'error_code':str(error),'verified_at':now()})
            else:store.update(item['id'],inspection={'error_code':type(error).__name__,'verified_at':now()},retry_condition='Agent inspection required; unsupported controls and unknown personal answers are not automatically retried.')
        workers.checkpoint(workflow_id,owner,index+1,'Reconciled existing application '+str(index+1))
    return {'state':'SYNCHRONIZED'}


def launch_sync_worker(db,application_id=None,application_ids=None):
    from .browser_workers import BrowserWorkers,fair_applications
    workers=BrowserWorkers(db);ids=[r['id'] for r in fair_applications(db,application_id)]
    if application_ids is not None:
        ids=[r['id'] for r in BrowserStore(db).list(include_history=True) if r['id'] in set(application_ids) and r['application_outcome']=='NOT_SUBMITTED'][:5]
    workflow_id=workers.enqueue('SYNC',ids)
    root=root_for(db);root.mkdir(parents=True,exist_ok=True)
    args=[sys.executable,'-m','job_agent.browser_applications','--db',str(db.path.resolve()),'--sync']
    if application_id:args+=['--only-application',application_id]
    args+=['--workflow',workflow_id]
    with (root/'worker.log').open('ab') as log:
        try:process=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except OSError:
            workers.finish(workflow_id,'ERROR','worker_launch_failed');raise ValueError('worker_launch_failed') from None
    workers.attach_pid(workflow_id,process.pid)
    return process.pid


def connect_login(db,portal):
    from playwright.sync_api import sync_playwright
    if portal not in CONNECT_URLS:raise ValueError('unsupported_login_portal')
    with workflow_lease(root_for(db)/'controller'):
        ensure_browser(db)
        with sync_playwright() as p:
            browser=p.chromium.connect_over_cdp(f'http://127.0.0.1:{PORT}',timeout=10000)
            page=browser.contexts[0].new_page();page.bring_to_front()
            page.goto(CONNECT_URLS[portal],wait_until='domcontentloaded',timeout=20000)
    return {'portal':portal,'state':'USER_LOGIN_REQUIRED','discovery':'Indirect alerts/manual exact imports; login does not enable scraping',
            'application_preparation':'Official employer Greenhouse/Lever routes supported; native portal applications manual'}


def main(argv=None):
    parser=argparse.ArgumentParser(description='Prepare up to five visible applications. You review and click Submit.')
    parser.add_argument('--db',default='data/jobs.sqlite3');parser.add_argument('--limit',type=int,default=5)
    parser.add_argument('--job',action='append');parser.add_argument('--worker');parser.add_argument('--batch')
    parser.add_argument('--no-upload',action='store_true');parser.add_argument('--connect',choices=CONNECT_URLS)
    parser.add_argument('--reinspect')
    parser.add_argument('--resume-application');parser.add_argument('--only-application');parser.add_argument('--sync',action='store_true');parser.add_argument('--workflow')
    args=parser.parse_args(argv);db=Database(args.db);store=BrowserStore(db)
    if args.sync:result=synchronize(db,args.only_application,args.workflow)
    elif args.resume_application:
        existing=store.get(args.resume_application);store.job(existing['job_id'],require_verified=True)
        if existing['state'] in {'SESSION_LOST','USER_REPORTED_SUBMITTED','SUBMISSION_CONFIRMED'}:raise ValueError('cannot_resume_without_progress_review')
        store.update(existing['id'],state='PREPARING')
        result=execute_batch(db,existing['batch_id'],not args.no_upload,existing['id'])
    elif args.reinspect:result=reinspect(db,args.reinspect)
    elif args.connect:result=connect_login(db,args.connect)
    else:
        batch_id=args.worker or args.batch
        if not batch_id:batch_id=store.batch(args.job,args.limit)['batch_id']
        result=run_worker_batch(db,batch_id,not args.no_upload,args.only_application,args.workflow)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()

"""Demonstrated rendered-form controls and layered preparation-only actions."""
import ipaddress
import json
import re
import socket
import time
from urllib.parse import urlsplit

ATS_HOSTS={'job-boards.greenhouse.io','boards.greenhouse.io','job-boards.eu.greenhouse.io',
           'jobs.lever.co','jobs.eu.lever.co','jobs.ashbyhq.com'}
STAGING_HOSTS={'grnhse-prod-jben-us-west-2.s3.us-west-2.amazonaws.com'}
FINAL=re.compile(r'submit|send application|finish|complete application|certif|attest|\bagree\b|consent|create account|sign up|accept terms',re.I)


def public_url(url,dns=socket.getaddrinfo):
    try:p=urlsplit(url)
    except ValueError:raise ValueError('unsafe_url') from None
    if p.scheme!='https' or not p.hostname or p.username or p.password or p.port not in {None,443}:
        raise ValueError('unsafe_url')
    if re.search(r'unsubscribe|autologin|logout|delete.account',p.path,re.I):raise ValueError('action_url_blocked')
    addresses=dns(p.hostname,443,type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):raise ValueError('private_network_destination')
    return url


GUARD_JS=r'''(() => {
 if(window.__jobPreparationInstalled){window.__jobPreparationActive=true;return;}
 window.__jobPreparationInstalled=true;window.__jobPreparationActive=true;
 document.addEventListener('submit',e=>{if(window.__jobPreparationActive){e.preventDefault();e.stopImmediatePropagation();}},true);
 document.addEventListener('keydown',e=>{if(window.__jobPreparationActive && e.key==='Enter' && e.target.tagName!=='TEXTAREA'){e.preventDefault();e.stopImmediatePropagation();}},true);
 document.addEventListener('click',e=>{let b=e.target.closest('button,input[type=submit],input[type=image]');
   if(window.__jobPreparationActive && b && (b.type==='submit'||b.type==='image')){e.preventDefault();e.stopImmediatePropagation();}},true);
 for(const name of ['submit','requestSubmit']){const original=HTMLFormElement.prototype[name];
   if(original)HTMLFormElement.prototype[name]=function(...args){if(!window.__jobPreparationActive)return original.apply(this,args);};}
})();'''

INVENTORY_JS=r'''() => [...document.querySelectorAll('input,textarea,select')].map((e,index)=>{
 const label=(e.labels?.length?[...e.labels].map(x=>x.innerText).join(' '):'')||e.getAttribute('aria-label')||
   (e.getAttribute('aria-labelledby')||'').split(' ').map(id=>document.getElementById(id)?.innerText||'').join(' ')||
   e.closest('.application-question,.field,.ashby-application-form-field-entry')?.querySelector('label,.application-label')?.innerText||'';
 const group=e.closest('fieldset')?.querySelector('legend')?.innerText||e.closest('.application-question')?.querySelector('.application-label')?.innerText||'';
 const instructions=(e.getAttribute('aria-describedby')||'').split(' ').map(id=>document.getElementById(id)?.innerText||'').join(' ');
 const control=e.closest('[class*="select__control"],[class$="-control"],[class*="select-control"]');
 const nearby=e.parentElement.nextElementSibling;
 const selected=control?.querySelector('[class*="single-value"],[class*="singleValue"]')||
   (nearby?.matches('[class*="single-value"],[class*="singleValue"]')?nearby:null);
 const customValue=selected?.textContent.trim()||(e.id==='country'?e.parentElement.parentElement.innerText.trim():'');
 return {id:e.id,name:e.name,index,tag:e.tagName.toLowerCase(),type:e.type||'text',role:e.getAttribute('role'),
  label:label.trim(),group,instructions,legal_control:!!e.closest('[data-consent],[data-attestation],.legal-declaration,.consent-field,[role="checkbox"]'),required:e.required||e.getAttribute('aria-required')==='true'||/\*/.test(label),
  max_length:e.maxLength||-1,visible:e.getAttribute('aria-hidden')!=='true'&&!!(e.offsetWidth||e.offsetHeight||e.getClientRects().length),
  disabled:e.disabled,value:e.type==='file'?[...e.files].map(f=>f.name):e.type==='checkbox'||e.type==='radio'?e.checked:e.getAttribute('role')==='combobox'?customValue:e.value,
  options:e.tagName==='SELECT'?[...e.options].map(o=>({label:o.text.trim(),value:o.value,disabled:o.disabled})):[],
  accept:e.accept||'',multiple:!!e.multiple,option_value:e.value};
})'''


def inventory(frame):return frame.evaluate(INVENTORY_JS)


def selected_value(control):
    return control.evaluate('''e=>{const c=e.closest('[class*="select__control"],[class$="-control"],[class*="select-control"]');const n=e.parentElement.nextElementSibling;const s=c?.querySelector('[class*="single-value"],[class*="singleValue"]')||(n?.matches('[class*="single-value"],[class*="singleValue"]')?n:null);return s?.textContent.trim()||(e.id==='country'?e.parentElement.parentElement.innerText.trim():'');}''')


def locate(frame,field):
    # IDs/names must be unique in this specific rendered frame and control type.
    scope=field['tag']
    if field.get('id'):locator=frame.locator(scope+'[id='+json.dumps(field['id'])+']')
    elif field.get('name'):
        locator=frame.locator(scope+'[name='+json.dumps(field['name'])+']')
        if field['type']=='radio':locator=frame.locator(scope+'[name='+json.dumps(field['name'])+'][value='+json.dumps(field['option_value'])+']')
    elif field.get('label'):locator=frame.get_by_label(field['label'],exact=True)
    else:raise ValueError('field_has_no_stable_identity')
    if locator.count()!=1:raise ValueError('ambiguous_field_locator')
    return locator


def classify_control(locator):
    info=locator.evaluate('(e)=>({tag:e.tagName.toLowerCase(),type:e.type||"",label:e.innerText||e.getAttribute("aria-label")||e.value||"",form:!!e.form,href:e.getAttribute("href"),formaction:e.getAttribute("formaction")})')
    if info['type'] in {'submit','image'} or info['formaction'] or FINAL.search(info['label']):return 'FINAL'
    if info['tag']=='a' and info['href']:return 'NAVIGATE'
    # Unknown button handlers are not safe navigation, regardless of their label.
    return 'AMBIGUOUS'


class Dispatcher:
    def __init__(self,frame):self.frame=frame

    def act(self,operation,field=None,value=None,locator=None):
        from .preparation_policy import human_control
        if operation not in {'FILL','SELECT','UPLOAD','NAVIGATE'}:raise ValueError('final_or_ambiguous_action_blocked')
        from .policy_hooks import check
        check('form',operation,field=field)
        if operation=='NAVIGATE':
            if locator is None or classify_control(locator)!='NAVIGATE':raise ValueError('final_or_ambiguous_action_blocked')
            raise ValueError('navigation_requires_coordinator_url_check')
        control=locate(self.frame,field)
        current_type=control.evaluate('(e)=>e.type')
        if human_control(field):raise ValueError('final_or_attestation_control_blocked')
        actual=[f for f in inventory(self.frame) if (field.get('id') and f['id']==field['id']) or (not field.get('id') and f['name']==field.get('name') and f['label']==field.get('label'))]
        if len(actual)!=1 or human_control(actual[0]):raise ValueError('final_or_attestation_control_blocked')
        if current_type in {'submit','image','button','hidden','password','checkbox'} or FINAL.search(field['label']):raise ValueError('final_or_attestation_control_blocked')
        if operation=='FILL':
            if field['type'] not in {'text','email','tel','url','number','textarea','search'}:raise ValueError('unsupported_fill_control')
            if field.get('max_length',-1)>0 and len(value)>field['max_length']:raise ValueError('answer_exceeds_character_limit')
            control.fill(value)
            actual=control.input_value()
            if field['type']=='tel':
                if re.sub(r'\D','',actual)!=re.sub(r'\D','',value):raise ValueError('phone_readback_mismatch')
            elif actual!=value:raise ValueError('field_readback_mismatch')
            return actual
        if operation=='SELECT':
            if field['type']=='radio':
                if field['label'].strip().casefold()!=value.casefold():raise ValueError('radio_option_mismatch')
                control.check()
                if not control.is_checked():raise ValueError('radio_readback_mismatch')
                return field['label']
            if field['tag']=='select':
                options=[o for o in field['options'] if not o['disabled'] and o['label'].casefold()==value.casefold()]
                if len(options)!=1:raise ValueError('option_membership_or_ambiguity')
                control.select_option(value=options[0]['value'])
                actual=control.locator('option:checked').inner_text().strip()
                if actual!=options[0]['label']:raise ValueError('selection_readback_mismatch')
                return actual
            if field.get('role')=='combobox':
                if control.is_editable():
                    control.fill(value)
                    # ArrowDown opens a searchable menu; never Enter.
                    control.press('ArrowDown')
                else:
                    # Yes/No React-select controls often use readonly inputs.
                    # Opening their menu is distinct from filling text.
                    control.click()
                option=self.frame.get_by_role('option',name=value,exact=True)
                if value=='India' and field['id']=='country':
                    visible_options=self.frame.get_by_role('option')
                    visible_options.first.wait_for(state='visible',timeout=5000)
                    exact_labels=[s for s in visible_options.all_text_contents() if re.fullmatch(r'India\s*(?:\(?\+91\)?)?',s.strip())]
                    if len(exact_labels)==1:option=self.frame.get_by_role('option',name=exact_labels[0],exact=True)
                option.wait_for(state='visible',timeout=5000)
                if option.count()!=1:raise ValueError('ambiguous_dropdown_option')
                option.click()
                actual=selected_value(control)
                # The phone-country widget shows the selected dialing prefix.
                if actual!=value:
                    prefix=control.evaluate('(e)=>e.parentElement.parentElement.innerText.trim()')
                    if not (field['id']=='country' and value=='India' and prefix=='+91'):raise ValueError('custom_selection_readback_mismatch')
                return value
            raise ValueError('unsupported_dropdown')
        if operation=='UPLOAD':
            if field['type']!='file':raise ValueError('wrong_upload_control')
            handle=control.element_handle()
            control.set_input_files(value)
            # Greenhouse replaces the input immediately after a successful stage.
            # Read the original element handle, never wait for a removed locator.
            return handle.evaluate('(e)=>[...e.files].map(f=>f.name)')


class NetworkBoundary:
    """Keep final application writes blocked while automation is active.

    Unknown autosave endpoints are blocked and reported, never inferred safe.
    Upload mode is scoped to one approved-file action and observed ATS hosts.
    """
    def __init__(self,ats_host,dns=socket.getaddrinfo):
        self.ats_host=ats_host;self.dns=dns;self.active=True;self.upload=False
        self.checked=set();self.blocked=0;self.upload_responses=[]
        self.requests=0;self.deadline=time.monotonic()+180

    def route(self,route):
        req=route.request
        try:
            self.requests+=1
            if self.requests>400 or time.monotonic()>self.deadline:raise ValueError('browser_request_or_runtime_budget_exhausted')
            p=urlsplit(req.url)
            if p.scheme in {'data','blob','about'}:return route.fallback()
            host=p.hostname or ''
            if host not in self.checked or req.is_navigation_request() or req.method not in {'GET','HEAD','OPTIONS'}:public_url(req.url,self.dns);self.checked.add(host)
            else:
                if p.scheme!='https' or p.username or p.password or p.port not in {None,443}:raise ValueError('unsafe_url')
            if req.is_navigation_request() and req.frame.parent_frame is None:
                if host not in ATS_HOSTS and host!=self.ats_host:raise ValueError('unexpected_application_redirect')
            if self.active and req.method not in {'GET','HEAD','OPTIONS'}:
                upload_path=(host in STAGING_HOSTS and p.path=='/') or (host==self.ats_host and re.search(r'/(?:upload|uploads|attachments|parseResume|parse-resume)(?:/|$)',p.path,re.I))
                if not (self.upload and req.method in {'POST','PUT'} and upload_path):raise ValueError('non_preparation_write_blocked')
            if self.active and re.search(r'/(?:submit|submitApplication|send-application)(?:/|$)',p.path,re.I):raise ValueError('final_action_route_blocked')
            return route.fallback()
        except (ValueError,OSError):
            self.blocked+=1;return route.abort()

    def response(self,response):
        p=urlsplit(response.url)
        if self.upload and response.request.method in {'POST','PUT'}:
            self.upload_responses.append({'host':p.hostname,'status':response.status})

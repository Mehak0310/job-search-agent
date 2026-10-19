/* One visible workspace view, with hash navigation and browser history. */
'use strict';
let emailLeadPage=1,emailLeadTimer=null;
document.querySelector('main').append($('tools-panel'));
document.querySelector('.workspace').after($('recommended-panel'));
const workspaceViews={
 'home-panel':['home-panel'],
 'browser-panel':['browser-panel'],
 'm3-panel':['m3-panel'],
 'opportunities-panel':['opportunities-panel','recommended-panel'],
 'professional-profile':['professional-profile','preferences-panel','background-panel'],
 'discovery-panel':['discovery-panel','m2d-panel','tools-panel'],
 'email-leads-panel':['email-leads-panel'],
 'tools-panel':['tools-panel']
};
function navigateWorkspace(id){
 if(!workspaceViews[id])id='opportunities-panel';
 if(window.activeWorkspaceId&&window.activeWorkspaceId!==id)message('');window.activeWorkspaceId=id;
 if(id==='opportunities-panel'){const cleared=$('source-filter').value==='gmail'||$('kind-filter').value==='EMAIL';if($('source-filter').value==='gmail')$('source-filter').value='';if($('kind-filter').value==='EMAIL')$('kind-filter').value='';if(cleared&&window.workspaceInitialized){saveFilters();guarded(refresh);}}
 for(const section of new Set(Object.values(workspaceViews).flat())){const node=$(section);if(node){node.hidden=!workspaceViews[id].includes(section);node.setAttribute('role','tabpanel');}}
 document.querySelector('.workspace').hidden=id!=='opportunities-panel';

 document.querySelector('.stats').hidden=id!=='opportunities-panel';
 document.querySelector('.intro').hidden=true;
 for(const tab of document.querySelectorAll('.workspace-nav a')){const selected=tab.hash==='#'+id||(id==='m3-panel'&&tab.hash==='#email-leads-panel');tab.id='tab-'+tab.hash.slice(1);tab.setAttribute('aria-controls',selected&&id==='m3-panel'?'m3-panel':tab.hash.slice(1));tab.setAttribute('aria-selected',String(selected));tab.tabIndex=selected?0:-1;}
 window.scrollTo(0,0);
 if(id==='email-leads-panel'&&typeof loadEmailLeads==='function')guarded(loadEmailLeads);
}
document.querySelector('.workspace-nav').addEventListener('keydown',event=>{const tabs=[...document.querySelectorAll('.workspace-nav a')],index=tabs.indexOf(document.activeElement);if(index<0)return;let next=index;if(event.key==='ArrowRight')next=(index+1)%tabs.length;else if(event.key==='ArrowLeft')next=(index+tabs.length-1)%tabs.length;else if(event.key==='Home')next=0;else if(event.key==='End')next=tabs.length-1;else return;event.preventDefault();tabs[next].focus();location.hash=tabs[next].hash;navigateWorkspace(tabs[next].hash.slice(1));});
window.addEventListener('hashchange',()=>navigateWorkspace(location.hash.slice(1)));
for(const tab of document.querySelectorAll('.workspace-nav a'))tab.addEventListener('click',()=>navigateWorkspace(tab.hash.slice(1)));
$('email-leads').replaceWith($('email-leads').cloneNode(true));
$('email-leads').addEventListener('click',()=>{location.hash='email-leads-panel';navigateWorkspace('email-leads-panel');message('Showing received email leads. Research status is shown for each alert.');});
navigateWorkspace(location.hash.slice(1));
$('source-filter').addEventListener('change',()=>{if($('source-filter').value==='gmail'){location.hash='email-leads-panel';navigateWorkspace('email-leads-panel');}});
$('kind-filter').addEventListener('change',()=>{if($('kind-filter').value==='EMAIL'){location.hash='email-leads-panel';navigateWorkspace('email-leads-panel');}});
async function loadEmailLeads(){
 clearTimeout(emailLeadTimer);
 $('email-research-status').textContent='Loading received email leads...';
 let result;try{result=await api('/api/email/leads?page='+emailLeadPage);}catch(error){$('email-research-status').textContent='Could not load received leads: '+error.message+'. Use Review received email leads to retry.';throw error;}
 $('email-research-status').textContent=`${result.total} received leads. ${result.named} have a usable title and job link; ${result.unresolved} are unresolved alerts. ${result.running} research tasks running. No automatic background discovery is installed.`;
 $('email-page-status').textContent=`Page ${result.page} of ${result.pages||1}`;$('email-previous').disabled=emailLeadPage<=1;$('email-next').disabled=emailLeadPage>=result.pages;
 $('email-lead-list').replaceChildren();
 for(const lead of result.items){const card=text('article','','job email-lead');card.append(text('h3',lead.title||'Unresolved email alert'),text('p',lead.company||'Employer not established from this alert','company'),text('strong',lead.research_state,'chip'));
   if(lead.url){const link=applicationLink(lead.url,lead.title?'Open '+lead.title:'Open original alert link');if(link)card.append(link);}
   card.append(text('p',lead.next_action),text('p',`Priority ${lead.queue_position||'pending'} | ${lead.message_category||'Unclassified received lead'} | ${lead.priority_reason||'Needs verification'} | Source: Gmail`));if(lead.researched_at)card.append(text('small','Last research: '+formatCheckpoint(lead.researched_at)));
   if(lead.official_candidates?.length){const details=document.createElement('details');details.append(text('summary','Potential official listings; identity still needs checking'));for(const candidate of lead.official_candidates){const link=applicationLink(candidate.url,candidate.title+' at '+candidate.company);if(link)details.append(link);}card.append(details);}
   card.append(text('p',`${lead.sender||'Sender not retained'} | ${lead.subject||'Subject not retained'} | ${lead.received_at||'Received date not retained'}`),text('p',`${lead.verification||lead.research_state} | ${lead.duplicate_status||'Duplicate check pending'}`));
   if(lead.gmail_url){const mail=applicationLink(lead.gmail_url,'Open received Gmail message');if(mail)card.append(mail);}
   if(lead.metadata_blocker)card.append(text('p',lead.metadata_blocker));
   const outcome=text('p','','lead-outcome');outcome.setAttribute('role','status');
   const research=text('button','Research this lead','secondary');research.addEventListener('click',()=>guarded(async()=>{research.disabled=true;outcome.textContent='Starting bounded research...';try{const r=await api('/api/email/leads/'+lead.id+'/research',{method:'POST'});outcome.textContent=r.selected?'Research queued; refresh to view the result.':'Already researched or blocked. See the recorded blocker above.';}catch(error){outcome.textContent='Research failed: '+error.message;throw error;}finally{research.disabled=false;}}));card.append(research);
   const importButton=text('button','Link verified opportunity','secondary');importButton.disabled=!lead.can_import;importButton.addEventListener('click',()=>guarded(async()=>{importButton.disabled=true;outcome.textContent='Checking opportunity link...';try{const r=await api('/api/email/leads/'+lead.id+'/import',{method:'POST'});outcome.textContent=r.state==='ALREADY_IMPORTED'?'Opportunity already linked; no duplicate created.':'Opportunity linked.';}catch(error){outcome.textContent='Import blocked: '+error.message;throw error;}finally{importButton.disabled=!lead.can_import;}}));card.append(importButton,outcome);
   $('email-lead-list').append(card);
 }
 if(result.running&&location.hash.startsWith('#email-leads-panel'))emailLeadTimer=setTimeout(()=>guarded(loadEmailLeads),3000);
}
$('email-previous').addEventListener('click',()=>{if(emailLeadPage>1){emailLeadPage--;guarded(loadEmailLeads);}});
$('email-next').addEventListener('click',()=>{emailLeadPage++;guarded(loadEmailLeads);});
$('research-email-leads').addEventListener('click',()=>guarded(async()=>{const button=$('research-email-leads');button.disabled=true;try{const result=await api('/api/email/research',{method:'POST'});message(`Alert research started for ${result.selected} leads. Unsupported portal access is reported explicitly.`);await loadEmailLeads();emailLeadTimer=setTimeout(()=>guarded(loadEmailLeads),2000);}finally{button.disabled=false;}}));

$('draft-close').addEventListener('click',()=>$('draft-dialog').close());

$('show-draft-packets').addEventListener('click',()=>{location.hash='m3-panel';navigateWorkspace('m3-panel');message('Showing draft approvals. Open an exact preview before approval.');});
$('show-received-leads').addEventListener('click',()=>{location.hash='email-leads-panel';navigateWorkspace('email-leads-panel');});

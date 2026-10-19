'use strict';
const $ = id => document.getElementById(id);
let statuses = [];
let pollTimer = null;
let searchBackground = null;
let currentPage = 1;
let jobRefreshVersion=0;
const filterIds=['search','status-filter','mode-filter','score-filter','title-filter','freshness-filter','location_bucket-filter','experience-filter','skills-filter','skill_mode-filter','category-filter','eligibility-filter','seniority-filter','activity-filter','employer-filter','priority-filter','source-filter','kind-filter','sort-filter'];
const saveFilters=()=>sessionStorage.setItem('jobFilters',JSON.stringify(Object.fromEntries(filterIds.map(id=>[id,$(id).value]))));
const restoreFilters=()=>{try{const saved=JSON.parse(sessionStorage.getItem('jobFilters')||'{}');for(const [id,value] of Object.entries(saved))if($(id))$(id).value=value;if(sessionStorage.getItem('fitSortPreference')!=='v1'){$('sort-filter').value='score_desc';sessionStorage.setItem('fitSortPreference','v1');saveFilters();}}catch{sessionStorage.removeItem('jobFilters');}};
const text = (tag, content, className = '') => { const el = document.createElement(tag); el.textContent = content; el.className = className; return el; };
const draftReason=code=>({incompatible_job:'role does not meet eligibility rules',confirmed_failed_mandatory_requirements:'role fails a verified mandatory requirement',gmail_connection_required:'Gmail connection required',previous_submission_blocks_repeat:'application already recorded as submitted',draft_preparation_check_failed:'document or packet check needs attention',required_document_unavailable:'approved document is unavailable',gmail_draft_outcome_uncertain:'Gmail outcome uncertain; check existing drafts'}[code]||String(code||'No eligible verified recruiter').replaceAll('_',' '));
function message(content, error = false) { $('message').textContent = content; $('message').className = error ? 'error' : ''; }
const inFlightReads=new Map();
function api(path,options={}){
  if((options.method||'GET').toUpperCase()!=='GET'){
    inFlightReads.clear();
    return requestLocal(path,options);
  }
  if(inFlightReads.has(path))return inFlightReads.get(path);
  const pending=requestLocal(path,options).finally(()=>{if(inFlightReads.get(path)===pending)inFlightReads.delete(path);});
  inFlightReads.set(path,pending);return pending;
}
async function requestLocal(path, options = {}) {
  const response = await fetch(path, options);
  let data;
  try { data = await response.json(); }
  catch { throw new Error(`The local server returned an unreadable response (HTTP ${response.status}). Refresh and try again.`); }
  if (!response.ok) throw new Error(data.detail || 'Request failed');
  return data;
}
function statusOptions(select, current) {
  for (const value of statuses) { const option = text('option', value.replaceAll('_', ' ')); option.value = value; option.selected = value === current; select.append(option); }
}
const plainState=value=>({READY_FOR_PORTAL_REVIEW:'Application text prepared',FULLY_VERIFIED_APPLICATION_READY:'Fully verified for application review',EMAIL_DRAFT_READY:'Eligible for draft review',PROMISING_NEEDS_VERIFICATION:'Promising; needs verification',EXCLUDED:'Excluded by verified evidence',ACCESS_BLOCKED:'Source access blocked',NEEDS_USER_INFORMATION:'Needs your information',CONTACT_VERIFICATION_PENDING:'Contact research pending',REVIEW_DRAFT_READY:'Application draft ready for review',GMAIL_DRAFT_PENDING:'Gmail draft outcome pending',GMAIL_DRAFT_SAVED:'Unsent Gmail draft saved',GMAIL_DRAFT_UNCERTAIN:'Gmail draft outcome uncertain',BLOCKED_INCOMPATIBLE:'Application preparation blocked'})[value]||String(value||'Unknown').replaceAll('_',' ').toLowerCase();
function postingAge(value){if(!value)return 'Posting date unknown';const hours=Math.max(0,(Date.now()-new Date(value).getTime())/36e5);if(hours<1)return 'Posted less than 1 hour ago';if(hours<24)return `Posted about ${Math.floor(hours)} hours ago`;return `Posted about ${Math.floor(hours/24)} days ago`;}
function bulletSection(title,values,empty='None recorded'){const section=text('section','', 'card-section');section.append(text('h4',title));const list=document.createElement('ul');for(const value of values.length?values:[empty])list.append(text('li',value));section.append(list);return section;}
async function refresh() {
  const refreshVersion=++jobRefreshVersion;
  const params = new URLSearchParams({q: $('search').value, min_score: $('score-filter').value, page: currentPage, page_size: 50});
  if ($('status-filter').value) params.set('status', $('status-filter').value);
  if ($('mode-filter').value) params.set('work_mode', $('mode-filter').value);
  for (const name of ['category', 'priority', 'source', 'kind', 'sort', 'eligibility', 'seniority', 'employer', 'activity', 'freshness', 'location_bucket', 'experience', 'skill_mode', 'title']) if ($(name + '-filter').value) params.set(name, $(name + '-filter').value);
  if ($('skills-filter').value) params.set('skills', $('skills-filter').value);
  const [result, overview, events] = await Promise.all([api('/api/jobs?' + params), api('/api/overview'), api('/api/audit?limit=8')]); if(refreshVersion!==jobRefreshVersion)return;const jobs=window.commandCenterJobFilter?window.commandCenterJobFilter(result.items):result.items;
  $('total').textContent = overview.total; $('shortlisted').textContent = overview.shortlisted; $('strong').textContent = overview.strong;
  $('result-count').textContent = window.commandCenterJobScope?.()?`${jobs.length} needing verification on this page | ${result.total} jobs in the current search; page through results or use Priority Queue for the full verification backlog`:`${result.total} opportunities match  |  showing ${jobs.length}`; $('page-status').textContent=`Page ${result.page} of ${result.pages || 1}`; $('previous-page').disabled=!result.has_previous; $('next-page').disabled=!result.has_next;
  $('jobs').replaceChildren();
  const employers=[...new Set(jobs.map(j=>j.company).filter(Boolean))].sort(); const currentEmployer=$('employer-filter').value; if(currentEmployer&&!employers.includes(currentEmployer))employers.push(currentEmployer); $('employer-filter').replaceChildren(text('option','All employers')); $('employer-filter').firstChild.value=''; for(const company of employers){const option=text('option',company);option.value=company;option.selected=company===currentEmployer;$('employer-filter').append(option);}
  if (!jobs.length) $('jobs').append(text('div', 'No jobs match these filters. Clear filters to include older postings, other experience ranges and jobs with unknown dates. Minimum fit is a score threshold; it does not change the sort order.', 'empty'));
  for (const job of jobs) {
    const view=job.card;const card=text('article','','job job-review-card');card.dataset.jobId=job.id;const top=text('div','','job-top');const info=text('div','');
    info.append(text('p',job.company||'Employer unknown','company-name'),text('h3',job.title||'Role needs verification'),text('p',`${job.location||'Location unknown'} | ${job.work_mode} | ${postingAge(job.published_at)}`,'company'));
    const primary=applicationLink(view.vacancy_url,job.listing_kind==='EMAIL'?'Open job (received alert)':'Open vacancy / Apply on company website')||text('span','Specific vacancy link unavailable','disabled-link');info.append(primary);
    const badges=text('div','','chips');badges.append(text('span',view.fit_label,'chip fit-chip'),text('span',view.requirement_assessment?.state&&view.requirement_assessment.state!=='PASS'?'Requirements: '+view.requirement_assessment.state:plainState(view.readiness),'chip'));for(const skill of view.matching_skills)badges.append(text('span',skill,'chip skill-chip'));if(!view.matching_skills.length)badges.append(text('span','Skill evidence pending review','chip'));info.append(badges);const score=text('div','','score');score.append(text('strong',view.fit_label==='Needs verification'?'Not assessed':job.match_score),text('small',view.fit_label==='Needs verification'?'JD research pending':'FIT / 100'));top.append(info,score);card.append(top);
    const comparison=text('div','','comparison-grid');comparison.append(bulletSection('Why it matches',view.matching_reasons),bulletSection('Important gaps',view.gaps,'No material gap recorded.'));
    const checks=text('section','','card-section employer-checks');checks.append(text('h4','Employer checks'));for(const check of view.employer_checks){const row=text('div','','check-row');row.append(text('strong',check.label),text('span',check.state,check.state==='Confirmed'?'check-pass':'check-pending'),text('small',check.detail),text('small',`Owner: ${check.owner}`));if(check.evidence_url){const source=applicationLink(check.evidence_url,'Evidence');if(source)row.append(source);}checks.append(row);}comparison.append(checks);card.append(comparison);
    const contactText=view.verified_contacts.length?view.verified_contacts.map(c=>`${c.name}: ${c.email}`).join(', ')+' | '+view.draft_status:view.draft_status;const candidateText=view.candidate_inputs.length?view.candidate_inputs.join('; ')+' (owner: You)':'No candidate answer is currently requested.';
    const statesBox=text('div','','application-states');for(const [label,value] of [['Application',view.application_status],['Recruiter / Gmail draft',contactText],['Candidate information',candidateText],['Submission',view.submission_status],['Next action',`${view.next_action} (owner: ${view.next_action_owner})`]]){const item=text('div','');item.append(text('strong',label),text('span',value));statesBox.append(item);}card.append(statesBox);
    if(view.packet_id){const prepared=document.createElement('details');prepared.className='prepared-inline';prepared.append(text('summary','Review prepared email, application text and questions'));const inside=text('div','','prepared-content');inside.append(text('h4','Email subject'),text('p',view.subject||'No subject prepared.'),text('h4','Prepared email'),text('pre',view.email_text||'No email prepared.'),text('h4','Portal supporting statement'),text('p',view.supporting_statement||'No statement prepared.'),text('h4','Actual employer questions'));if(!view.questions.length)inside.append(text('p','No employer questions have been imported.'));for(const q of view.questions)inside.append(text('p',`${q.question}: ${q.answer||'Needs your answer'}`));prepared.append(inside);card.append(prepared);}
    const actions=text('div','','job-actions');const shortlist=text('button',job.status==='SHORTLISTED'?'Shortlisted':'Shortlist','secondary');shortlist.disabled=job.status==='SHORTLISTED';shortlist.addEventListener('click',()=>guarded(()=>changeStatus(job.id,'SHORTLISTED')));actions.append(shortlist);
    if(view.browser_preparation){const browser=view.browser_preparation;card.append(text('p',`Browser application: ${browser.state.replaceAll('_',' ')}  |  Last checkpoint ${new Date(browser.updated_at).toLocaleString()}`),bulletSection('Form answers still needed',browser.missing,'No unanswered required control recorded.'),bulletSection('Application documents',browser.documents.map(d=>`${d.name}: ${d.verified?'filename and acceptance verified':'needs reconciliation'}`),'No verified document acceptance recorded.'));const focus=text('button','Switch to application tab','secondary');focus.addEventListener('click',()=>guarded(async()=>{const result=await api('/api/browser/applications/'+browser.id+'/switch',{method:'POST'});message(result.state==='SESSION_LOST'?'Saved application tab is unavailable. Review progress before reconstructing.':'Application tab selected in the dedicated browser.');}));actions.append(focus);}
    if(!view.packet_id&&view.job_key&&view.fit_label!=='Needs verification'){const prepare=text('button','Prepare application text','secondary');prepare.addEventListener('click',()=>guarded(async()=>{await api('/api/m3/packets/job/'+encodeURIComponent(view.job_key),{method:'POST'});message('Application text prepared locally. Nothing was sent.');await Promise.all([refresh(),refreshM3()]);}));actions.append(prepare);}else if(view.packet_id){const edit=text('button','Review or edit application','secondary');edit.addEventListener('click',()=>guarded(()=>showPacket(view.packet_id)));actions.append(edit);}
    if(view.draft_allowed&&view.packet_id){const draft=text('button','Preview Gmail draft','secondary');draft.addEventListener('click',()=>guarded(()=>openDraftPreview(view.packet_id)));actions.append(draft);}
    if(view.packet_id && !view.review_hidden && !['EXCLUDED','ACCESS_BLOCKED'].includes(view.readiness) && job.status!=='SUBMITTED'){
      const browserPrepare=text('button','Prepare browser application','secondary');browserPrepare.addEventListener('click',()=>guarded(async()=>{const batch=await api('/api/browser/batches',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({job_ids:[job.id],limit:1})});message(batch.selected?'Browser preparation started. Answers/uploads may reach the employer; you review and submit.':'Existing preparation or eligibility blocker; see browser progress.');await refreshBrowser();}));actions.append(browserPrepare);
    }
    if(!view.review_hidden)actions.append(unavailableButton(job.id));
    const label=text('label','Manual tracking status');const select=document.createElement('select');select.setAttribute('aria-label',`Manual status for ${job.title}`);statusOptions(select,job.status);select.addEventListener('change',()=>guarded(async()=>{try{await changeStatus(job.id,select.value);}catch(error){select.value=job.status;throw error;}}));label.append(select);actions.append(label);card.append(actions);$('jobs').append(card);
  }
  $('audit').replaceChildren();
  if (!events.length) $('audit').append(text('p', 'Your activity will appear here.'));
  for (const event of events) { const entry = text('div', '', 'activity'); entry.append(text('strong', event.action.replaceAll('_', ' ')), text('span', JSON.stringify(event.details)), text('time', new Date(event.created_at).toLocaleString())); $('audit').append(entry); }
}
async function refreshM2D(){const [summary,sources]=await Promise.all([api('/api/m2d/summary'),api('/api/m2d/sources')]);$('m2d-status').textContent=`${summary.status} | configured ${summary.coverage.configured} | attempted ${summary.coverage.attempted} | meaningful ${summary.coverage.meaningful} | exhaustive ${summary.coverage.exhaustive} | distinct jobs ${summary.distinct_jobs} | observations ${summary.observations}`;$('m2d-readiness').replaceChildren();for(const [status,count] of Object.entries(summary.readiness))$('m2d-readiness').append(text('article',`${status.replaceAll('_',' ')}: ${count}`,'source-card'));$('m2d-coverage').replaceChildren();for(const source of sources){const card=text('article','', 'source-card');card.append(text('strong',source.display_name),text('small',`${source.stream} | ${source.implementation_state}`),text('small',`Coverage: ${source.coverage_status.replaceAll('_',' ').toLowerCase()}`),text('small',source.blocker?`Blocker: ${source.blocker}`:source.implementation_state==='MANUAL_IMPORT_ONLY'?'Direct automated access is unavailable. Received alerts and exact official employer routes are supported.':source.implementation_state==='NOT_IMPLEMENTED'?'No connector exists yet; no access time is scheduled.':`Backlog: ${source.backlog}. Use Run discovery for a bounded supported-source run.`));$('m2d-coverage').append(card);}}
const checkNames={direct_permanent_payroll:'Direct, permanent employment',headcount:'Employer size',india_eligible:'India eligibility',mandatory_requirements:'Required experience and skills',active:'Vacancy still open'};
const readableCheck=value=>checkNames[value]||value.replaceAll('_',' ');
function applicationLink(url,label='Open application'){
  try{const parsed=new URL(url);if(!['https:','http:'].includes(parsed.protocol)||parsed.username||parsed.password)return null;
    const link=text('a',label,'vacancy-link');link.href=parsed.href;link.target='_blank';link.rel='noopener noreferrer';return link;
  }catch{return null;}
}
function fitOverview(reasons,gaps){
  const section=text('div','','fit-overview');
  section.append(text('h4','Why this role fits'),text('p',reasons.length?reasons.join(' '):'No specific matching evidence recorded; review the role requirements.'));
  section.append(text('h4','Gaps to review'),text('p',gaps.length?gaps.join('; '):'No gaps recorded. This does not verify all requirements.'));
  return section;
}
async function dismissUnavailable(jobId){
  await api('/api/jobs/'+encodeURIComponent(jobId)+'/review-dismissal',{method:'POST'});
  message('Removed from review because you reported an unavailable application link. History is preserved.');
  await Promise.all([refreshM3(),refreshBrowser(),refreshRecommendations(),refresh()]);
}
function unavailableButton(jobId){
  const button=text('button','Remove unavailable job','secondary');
  button.addEventListener('click',()=>guarded(()=>dismissUnavailable(jobId)));return button;
}
async function createAutomaticDraft(packetId){return openDraftPreview(packetId);}
async function openDraftPreview(packetId){
 message('Loading exact draft preview...');
 const preview=await api('/api/m3/packets/'+packetId+'/draft-preview',{method:'POST'});
 const dialog=$('draft-dialog'),body=$('draft-preview-body');body.replaceChildren();
 for(const [label,value] of [['Recipient',preview.recipient||'No verified recipient'],['Recipient evidence',JSON.stringify(preview.recipient_evidence||{})],['Vacancy',preview.title+' at '+preview.company],['Eligibility',preview.eligibility],['Subject',preview.subject],['Message',preview.text],['Attachment policy',preview.attachment_policy]]){body.append(text('h3',label),text(label==='Message'?'pre':'p',value));}
 const htmlDetails=document.createElement('details');htmlDetails.append(text('summary','Exact HTML alternative (literal source)'),text('pre',preview.html||''));body.append(htmlDetails);
 if(preview.blockers.length)body.append(text('p','Blocked: '+preview.blockers.join('; '),'manual'));
 const approve=$('draft-approve');approve.disabled=preview.blockers.length>0;
 $('draft-preview-status').textContent=preview.live_creation_enabled?'Review the exact content before approving.':'R2 verification mode: live Gmail creation is disabled. Approval works only with the isolated test adapter.';
 approve.onclick=()=>guarded(async()=>{approve.disabled=true;try{const saved=await api('/api/m3/draft-approvals',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({preview_id:preview.preview_id,approved:true})});$('draft-preview-status').textContent='Unsent draft saved: '+saved.gmail_draft_id;if(saved.gmail_url){const link=applicationLink(saved.gmail_url,'Review saved Gmail draft');if(link)body.append(link);}await refreshM3();}catch(error){$('draft-preview-status').textContent='Draft not created: '+error.message;throw error;}finally{approve.disabled=false;}});
 if(!dialog.open)dialog.showModal();message('Exact draft preview loaded.');
 return preview;
}
async function refreshM3(){
  const [packets,gmail]=await Promise.all([api('/api/m3/packets'),api('/api/m3/gmail/status')]);
  $('m3-status').textContent=`${packets.length} prepared application texts. Gmail drafts require approval of the exact preview. Live creation is disabled pending separate authorization.`;
  $('application-queue').replaceChildren();
  for(const packet of packets){
    const card=text('article','','job packet-card');
    const pending=packet.missing_information||[];
    card.append(text('h3',packet.title),text('p',packet.company,'company'),text('span',pending.length?'Checks needed':'Text prepared','chip'));
    card.append(fitOverview(packet.fit_summary||[],packet.gaps||[]));
    if(pending.length)card.append(text('div','Outstanding checks: '+pending.map(readableCheck).join('; '),'manual'));
    const actions=text('div','','job-actions');const apply=applicationLink(packet.canonical_application_url||packet.application_url);if(apply)actions.append(apply);else actions.append(text('span','Application link unavailable','disabled-link'));
    const preview=text('button','Preview Gmail draft','secondary');preview.addEventListener('click',()=>guarded(()=>openDraftPreview(packet.packet_id)));actions.append(preview);const view=text('button','Edit prepared text','secondary');view.addEventListener('click',()=>guarded(()=>showPacket(packet.packet_id)));actions.append(view);if(packet.job_id)actions.append(unavailableButton(packet.job_id));card.append(actions);$('application-queue').append(card);
  }
}
function escapeEmailHTML(value){return value.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('\n','<br>');}
async function showPacket(id){const packet=await api('/api/m3/packets/'+id),v=packet.version_data;const body=$('detail-body');$('detail-title').textContent=`Application: ${packet.title}`;body.replaceChildren(text('div',`${packet.submission_label||'Not submitted'} | ${packet.status.replaceAll('_',' ')}  |  Version ${packet.current_version}  |  Text prepared is not an application submission.`,'manual'),text('p','Eligibility and information to confirm: '+(packet.missing_information.join(', ')||'No packet-level gaps recorded.')),text('h3','Fit evidence'),text('p',v.fit_summary.join(' ')),text('h3','Gaps'),text('p',v.gaps.join(', ')||'No skill gaps identified by the deterministic matcher.'));const form=document.createElement('form');const subject=document.createElement('input');subject.value=v.subject;subject.id='packet-subject';const email=document.createElement('textarea');email.value=v.email_text;email.id='packet-email';email.rows=12;const statement=document.createElement('textarea');statement.value=v.supporting_statement;statement.id='packet-statement';statement.rows=6;form.append(text('label','Subject'),subject,text('label','Application email'),email,text('label','Portal supporting statement'),statement);const save=text('button','Save new local version');save.type='submit';form.append(save);form.addEventListener('submit',event=>{event.preventDefault();guarded(async()=>{await api('/api/m3/packets/'+id,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({subject:subject.value,email_text:email.value,email_html:email.value===v.email_text?v.email_html:escapeEmailHTML(email.value),supporting_statement:statement.value})});message('Saved a new local packet version. Existing Gmail drafts were not changed.');$('detail-dialog').close();await refreshM3();});});for(const [label,id] of [['Subject','packet-subject'],['Application email','packet-email'],['Portal supporting statement','packet-statement']]){const el=[...form.querySelectorAll('label')].find(e=>e.textContent===label);el.htmlFor=id;}body.append(form,text('h3','Actual employer questions'));if(!packet.questions.length)body.append(text('p','No employer questions have been imported. No questions were invented.'));for(const q of packet.questions)body.append(text('p',`${q.question}  |  ${q.answer_status||'unanswered'}  |  ${q.answer||'Needs your information'}`));body.append(text('h3','Contact evidence'));if(!packet.contacts.length)body.append(text('p','No verified role-related recipient. Portal preparation remains available; Gmail drafting is blocked.'));for(const c of packet.contacts)body.append(text('p',`${c.name}  |  ${c.role_relevance}  |  ${c.verification_status}`));$('detail-dialog').showModal();}async function changeStatus(id, status) {
  await api(`/api/jobs/${id}/status`, {method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({status})});
  message(`Manual status saved: ${status.replaceAll('_', ' ')}. No application was sent.`); await Promise.all([refresh(),refreshM3(),refreshBrowser(),refreshRecommendations()]);
}
async function refreshRecommendations() {
  const params=new URLSearchParams({limit:'25'}); if($('recommendation-eligibility').value)params.set('eligibility',$('recommendation-eligibility').value); if($('recommendation-role').value)params.set('role_family',$('recommendation-role').value);
  const jobs=await api('/api/recommendations?'+params); $('recommendations').replaceChildren(); $('recommendation-status').textContent=`${jobs.length} ranked recommendations. Scores are not hiring probabilities.`;
  for(const job of jobs){const card=text('article','', 'job'); const top=text('div','', 'job-top'); const heading=text('h3',''); const link=text('button',job.title); link.addEventListener('click',()=>guarded(()=>showDetail(job.id))); heading.append(link); top.append(heading,text('strong',`${job.recommendation_score.toFixed(1)}/100`,'score')); const chips=text('div','', 'chips'); chips.append(text('span',job.gate_state==='ELIGIBLE'?'India eligible':'Eligibility unverified','chip'),text('span',job.recommendation_confidence+' evidence','chip'),text('span',job.ai_state,'chip')); const why=job.recommendation_explanation; card.append(top,text('p',`${job.company} | ${job.location}`),chips,fitOverview([...(why.why||[]),...(why.matched_skills?.length?['Matching skills: '+why.matched_skills.join(', ')]:[])],why.missing_or_uncertain||[]));const apply=applicationLink(job.canonical_application_url||job.application_url);if(apply)card.append(apply); $('recommendations').append(card);}
}
async function showDetail(id) {
  const job = await api(`/api/jobs/${id}`); $('detail-title').textContent = job.title;
  const body = $('detail-body'); body.replaceChildren(text('p', `${job.company} | ${job.location} | ${job.work_mode}`), text('p', `Fit ${job.match_score}/100 | ${job.is_sample ? 'Fictional sample' : job.listing_kind === 'LIVE' ? 'Live public listing' : 'Imported opportunity'}`), text('div', `Status: ${job.status.replaceAll('_', ' ')} | Manual tracking. ${job.submission_label||'Not submitted'}.`, 'manual'));
  if (job.listing_kind === 'LIVE') body.append(text('p', `Published: ${job.published_at ? new Date(job.published_at).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'}) : 'unknown'}  |  First discovered: ${new Date(job.first_seen).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'})}  |  Source updated: ${job.source_updated_at ? new Date(job.source_updated_at).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'}) : 'unknown'}`), text('p', `${job.category}  |  ${job.priority}  |  ${job.seniority_level}  |  Match confidence: ${job.match.confidence}  |  Activity: ${job.activity_status}`), text('div', `India: ${job.eligibility_state} (${job.eligibility_confidence})  |  ${job.eligibility_explanation} Evidence: ${job.eligibility_evidence}`, 'manual'));
  for (const [heading, values] of [['Matching reasons', job.match.reasons], ['Missing requirements / unknowns', job.match.missing_requirements], ['Potential disqualifiers', job.match.potential_disqualifiers]]) {
    const section = text('section', '', 'detail-section'); section.append(text('h3', heading)); const list = document.createElement('ul'); for (const value of values.length ? values : ['None identified']) list.append(text('li', value)); section.append(list); body.append(section);
  }
  const description = text('section', '', 'detail-section'); description.append(text('h3', 'Description'), text('p', job.description || 'No description supplied.', 'description')); body.append(description);
  const sources = text('section', '', 'detail-section'); sources.append(text('h3', 'Source references'));
  for (const source of job.sources) {
    const row = text('p', `${source.source}${source.source_job_id ? ' | ' + source.source_job_id : ''} `);
    const anchor=applicationLink(source.listing_url,'View employer listing (no submission)')||applicationLink(source.application_url,'View employer listing (no submission)');if(anchor)row.append(anchor);else row.append(text('span','Listing link unavailable','disabled-link'));
    sources.append(row);
  }
  body.append(sources); const history = text('section', '', 'detail-section'); history.append(text('h3', 'Status history')); for (const entry of job.history) history.append(text('p', `${entry.status.replaceAll('_', ' ')} | ${new Date(entry.created_at).toLocaleString()}`)); body.append(history); $('detail-dialog').showModal();
}
async function guarded(action) { try { await action(); } catch (error) { message(error.message, true); } }
const split = value => value.split(';').map(s => s.trim()).filter(Boolean);
function renderCandidate(candidate){
  $('candidate-locations').value=candidate.preferred_locations.join('; ');$('candidate-years').value=candidate.total_experience_years === null ? '' : candidate.total_experience_years;
  $('profile-version').textContent=`Profile version ${candidate.version}  |  ${candidate.professional_ai_confirmed?'professional AI work confirmed':'AI scope needs review'}`;
  $('resume-status').textContent=candidate.resume_attached?`${candidate.resume_display_name}  |  ${candidate.resume_display_version||'version not recorded'}  |  ${candidate.resume_proposals_pending} of ${candidate.resume_proposals_total} facts need review`:'No resume attached';
  $('professional-ai-summary').replaceChildren(text('h3','AI application engineering'),text('p','Professional experience  |  LLM: '+(candidate.technology_years.llm == null ? 'unknown' : candidate.technology_years.llm)+' years  |  employer/client/production attribution is recorded separately.'));
  for(const item of candidate.professional_ai_summary)$('professional-ai-summary').append(text('p',item));
  $('skill-domains').replaceChildren();const shown=new Set();
  for(const [domain,skills] of Object.entries(candidate.skill_domains)){const group=text('section','', 'skill-domain');group.append(text('h4',domain));const chips=text('div','', 'chips');for(const skill of skills){shown.add(skill.id);const label=skill.display_name+(skill.years!=null?`  |  ${skill.years} years`:'');const chip=text('span',label,'chip skill-chip');chip.title=`${skill.sources.length} evidence source${skill.sources.length===1?'':'s'}`;chips.append(chip);}group.append(chips);$('skill-domains').append(group);}
  $('candidate-additional').value=candidate.professional_skills.filter(skill=>!shown.has(skill)).join('; ');
  $('proposal-progress').textContent=`${candidate.resume_proposals_pending} needs review  |  ${candidate.resume_proposals_total-candidate.resume_proposals_pending} resolved or linked to confirmed facts`;
}
async function loadCandidate(){const candidate=await api('/api/candidate-profile');renderCandidate(candidate);await refreshFacts();}
async function initialize() {
  const loadStatuses=api('/api/statuses').then(values=>{statuses=values;statusOptions($('status-filter'),'');});
  const loadSources=sectionLoad('discovery-panel',refreshSources);
  await Promise.allSettled([
    sectionLoad('professional-profile',async()=>{const profile=await api('/api/profile');for(const [id,field] of [['titles','target_titles'],['skills','skills'],['locations','locations'],['exclusions','exclusions']])$('profile-'+id).value=profile[field].join('; ');$('profile-experience').value=profile.experience_years==null?'':profile.experience_years;for(const checkbox of document.querySelectorAll('[name=profile-mode]'))checkbox.checked=profile.work_modes.includes(checkbox.value);await loadCandidate();}),
    sectionLoad('background-panel',async()=>{searchBackground=await api('/api/search-background');$('background-total').value=searchBackground.total_years;$('background-backend').value=searchBackground.backend_years;$('background-established').value=searchBackground.established_skills.join('; ');$('background-developing').value=searchBackground.developing_skills.join('; ');$('background-note').textContent=searchBackground.evidence_note;}),
    loadSources,sectionLoad('m2d-panel',refreshM2D),sectionLoad('m3-panel',refreshM3),sectionLoad('recommended-panel',refreshRecommendations),sectionLoad('opportunities-panel',async()=>{await loadStatuses;await loadSources;restoreFilters();await refresh();}),
    sectionLoad('discovery-panel',async()=>{const latest=await api('/api/discovery/latest');if(latest){renderRun(latest);if(latest.status==='RUNNING')pollRun(latest.id);}})
  ]);
}
let sectionLoadSequence=0;
async function sectionLoad(id,load){const panel=$(id),key=load.name||'loader-'+(++sectionLoadSequence);const find=()=>[...panel.querySelectorAll(':scope>.section-error')].find(n=>n.dataset.loader===key);try{await load();find()?.remove();}catch(error){let note=find();if(!note){note=text('p','','section-error');note.dataset.loader=key;note.setAttribute('role','status');panel.prepend(note);}note.textContent='This section could not load: '+error.message+'. Retry this view to refresh.';}}
async function refreshSources() {
  const sources = await api('/api/sources'); const current = $('source-filter').value; $('source-filter').replaceChildren(text('option', 'All sources')); $('source-filter').firstChild.value = '';
  const gmailOption=text('option','Received Gmail leads');gmailOption.value='gmail';gmailOption.selected=current==='gmail';$('source-filter').append(gmailOption);
  $('source-health').replaceChildren();
  for (const source of sources) {
    const option = text('option', source.company); option.value = source.id; option.selected = source.id === current; $('source-filter').append(option);
    const card = text('article', '', 'source-card'); const label = text('label', ''); const checkbox = document.createElement('input'); checkbox.type = 'checkbox'; checkbox.checked = source.enabled; checkbox.setAttribute('aria-label', `Enable ${source.company}`);
    checkbox.addEventListener('change', () => guarded(async () => { checkbox.disabled = true; try { await api('/api/sources/' + source.id, {method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({enabled: checkbox.checked})}); await refreshSources(); } catch (error) { checkbox.checked = source.enabled; throw error; } finally { checkbox.disabled = false; } }));
    label.append(checkbox, text('span', `${source.company}  |  ${source.provider}`)); card.append(label, text('small', `Health: ${source.health}${source.last_error ? '  |  ' + source.last_error : ''}`), text('small', `Verified: ${source.verified ? new Date(source.verified_at).toLocaleString() : 'No'}  |  India roles: ${source.india_relevant === null ? 'unknown' : source.india_relevant ? 'present' : 'not observed'}`), text('small', source.verification_evidence || 'No verification evidence'), text('small', 'Last successful scan: ' + (source.last_success ? new Date(source.last_success).toLocaleString() : 'Never')), text('small', 'Next eligible: ' + (source.next_scan_after ? new Date(source.next_scan_after).toLocaleString() : 'Now'))); $('source-health').append(card);
  }
}
function renderRun(run) {
  const m = run.metrics; $('run-discovery').disabled = run.status === 'RUNNING';
  $('discovery-status').textContent = `${run.status}  |  New ${m.new_jobs}  |  Updated ${m.updated_jobs}  |  Unchanged ${m.unchanged_jobs}  |  Duplicates ${m.duplicates}  |  Failed ${m.failed_sources}  |  Requests ${m.requests}  |  ${m.response_bytes} bytes  |  Eligible ${m.india_eligible_jobs ?? 0}  |  Unknown ${m.unknown_eligibility_jobs ?? 0}${run.duration_seconds !== null ? '  |  ' + run.duration_seconds + 's' : ''}`;
}
async function pollRun(id) {
  clearTimeout(pollTimer);
  try { const run = await api('/api/discovery/runs/' + id); renderRun(run); if (run.status === 'RUNNING') { pollTimer = setTimeout(() => pollRun(id), 2000); } else { await Promise.all([refresh(), refreshSources()]); } } catch (error) { $('run-discovery').disabled = false; message(error.message, true); }
}
$('run-discovery').addEventListener('click', () => guarded(async () => { $('run-discovery').disabled = true; $('discovery-status').textContent = 'Starting bounded discovery...'; try { const response = await api('/api/discovery/runs', {method: 'POST'}); await pollRun(response.run_id); } catch (error) { $('run-discovery').disabled = false; throw error; } }));
$('background-form').addEventListener('submit', event => { event.preventDefault(); guarded(async () => { searchBackground = await api('/api/search-background', {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({...searchBackground, total_years: Number($('background-total').value), backend_years: Number($('background-backend').value), established_skills: split($('background-established').value), developing_skills: split($('background-developing').value)})}); message('Live search background saved and existing live listings rescored.'); await refresh(); }); });
$('filters').addEventListener('submit', event => { event.preventDefault(); currentPage=1; saveFilters(); guarded(refresh); });
$('previous-page').addEventListener('click',()=>{if(currentPage>1){currentPage--;guarded(refresh);}}); $('next-page').addEventListener('click',()=>{currentPage++;guarded(refresh);});
$('clear-filters').addEventListener('click',()=>{ $('filters').reset(); sessionStorage.removeItem('jobFilters'); $('freshness-filter').value=''; $('experience-filter').value=''; saveFilters(); currentPage=1; guarded(refresh); });
$('reset-preferences').addEventListener('click',()=>{ $('filters').reset(); $('freshness-filter').value='48h'; $('experience-filter').value='5-8'; $('location_bucket-filter').value='DELHI_NCR,GURUGRAM,NOIDA,GREATER_NOIDA,MOHALI,CHANDIGARH,REMOTE_INDIA'; $('sort-filter').value='score_desc'; saveFilters(); currentPage=1; guarded(refresh); });
$('refresh').addEventListener('click', () => guarded(refresh));
$('prepare-applications').addEventListener('click',()=>guarded(async()=>{const result=await api('/api/m3/packets/prepare',{method:'POST'});message(`Application preparation: ${result.prepared} prepared, ${result.unchanged} unchanged, ${result.failed.length} failed.`);await refreshM3();}));
$('export-applications').addEventListener('click',()=>guarded(async()=>{const result=await api('/api/m3/export',{method:'POST'});message(`Local review workbook ${result.path} created with ${result.packets} packets. Upload status: ${result.upload_status}.`);}));
$('close-dialog').addEventListener('click', () => $('detail-dialog').close());
$('import-form').addEventListener('submit', event => { event.preventDefault(); guarded(async () => {
  const file = $('import-file').files[0]; if (!file) throw new Error('Choose a JSON or CSV file.'); if (file.size > 2 * 1024 * 1024) throw new Error('File exceeds the 2 MiB limit.');
  const data = new FormData(); data.append('file', file); const button = event.target.querySelector('button'); button.disabled = true;
  try { const report = await api('/api/import', {method: 'POST', body: data}); $('import-result').textContent = JSON.stringify(report, null, 2); message(`Import complete: ${report.created} new, ${report.duplicates} duplicates, ${report.invalid} invalid.`); await refresh(); } finally { button.disabled = false; }
}); });
$('profile-form').addEventListener('submit', event => { event.preventDefault(); guarded(async () => {
  const profile = {target_titles: split($('profile-titles').value), skills: split($('profile-skills').value), locations: split($('profile-locations').value), exclusions: split($('profile-exclusions').value), experience_years: $('profile-experience').value === '' ? null : Number($('profile-experience').value), work_modes: [...document.querySelectorAll('[name=profile-mode]:checked')].map(el => el.value)};
  await api('/api/profile', {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(profile)}); message('Preferences saved. Existing jobs have been rescored.'); await refresh();
}); });
$('refresh-recommendations').addEventListener('click',()=>guarded(async()=>{const metrics=await api('/api/recommendations/refresh',{method:'POST'}); $('recommendation-status').textContent=`Scored ${metrics.jobs_scored}; cache hit rate ${Math.round(metrics.cache_hit_rate*100)}%; LLM calls ${metrics.llm_calls}.`; await refreshRecommendations();}));
$('recommendation-eligibility').addEventListener('change',()=>guarded(refreshRecommendations)); $('recommendation-role').addEventListener('change',()=>guarded(refreshRecommendations));
$('candidate-form').addEventListener('submit', event => {
  event.preventDefault(); guarded(async () => {
    const current=await api('/api/candidate-profile');
    const {resume_attached,resume_reviewed,resume_name,resume_display_name,resume_display_version,resume_proposals_total,resume_proposals_pending,skill_domains,...preserved}=current; const domainSkills=Object.values(current.skill_domains).flat().map(item=>item.id);const payload={...preserved,professional_skills:[...new Set([...domainSkills,...split($('candidate-additional').value)])],total_experience_years:$('candidate-years').value===''?null:Number($('candidate-years').value),preferred_locations:split($('candidate-locations').value),reviewed:current.resume_proposals_pending===0};
    await api('/api/candidate-profile',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}); message('Candidate profile version saved locally. Recommendations refreshed.'); await refreshRecommendations();
  });
});
$('resume-form').addEventListener('submit', event => {
  event.preventDefault(); guarded(async () => {
    const body=new FormData(); body.append('file',$('resume-file').files[0]); await api('/api/candidate-profile/resume',{method:'POST',body}); $('resume-status').textContent='Resume attached locally; review facts before accepting them.'; message('Local resume reference stored. The original resume was not modified.');
  });
});
async function refreshFacts(){const facts=await api('/api/candidate-profile/facts');$('fact-proposals').replaceChildren();for(const fact of facts){const row=text('article','', 'fact-card');const state=fact.link_state==='USER_CONFIRMED_MATCH'?'Confirmed by user  |  parser proposal still awaiting an explicit decision':fact.status==='PENDING'?'Needs review':fact.status==='ACCEPTED'?'Accepted by user':'Rejected by user';row.append(text('strong',fact.value),text('span',state,'fact-state'));const details=document.createElement('details');details.append(text('summary','Evidence and technical details'),text('p',`${fact.source_ref}  |  extraction confidence ${fact.confidence}  |  ${fact.category}  |  extraction ${fact.extraction_id.slice(0,8)}`));row.append(details);if(fact.status==='PENDING'){const edit=document.createElement('input');edit.value=fact.value;edit.setAttribute('aria-label',`Reviewed value for ${fact.value}`);row.append(edit);const actions=text('div','', 'fact-actions');for(const action of ['ACCEPTED','REJECTED']){const button=text('button',action==='ACCEPTED'?'Accept fact':'Reject','secondary');button.type='button';button.addEventListener('click',()=>guarded(async()=>{const payload={action};if(action==='ACCEPTED')payload.reviewed_value=edit.value;await api('/api/candidate-profile/facts/'+fact.id,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});await loadCandidate();}));actions.append(button);}row.append(actions);}$('fact-proposals').append(row);}}
$('parse-resume').addEventListener('click',()=>guarded(async()=>{const result=await api('/api/candidate-profile/resume/parse',{method:'POST'});message(`Local extraction proposed ${result.proposals} facts. Review each before it affects the profile.`);await refreshFacts();}));
function formatCheckpoint(value){const date=new Date(value);return value&&!Number.isNaN(date.valueOf())?new Intl.DateTimeFormat('en-IN',{dateStyle:'medium',timeStyle:'short',timeZone:'Asia/Kolkata'}).format(date)+' IST':'Not inspected';}
for(const portal of ['linkedin','naukri'])$('connect-'+portal).addEventListener('click',async()=>{
  const button=$('connect-'+portal),status=$('connection-status');
  for(const name of ['linkedin','naukri'])$('connect-'+name).disabled=true;
  status.className='manual';status.textContent=`Opening ${portal==='linkedin'?'LinkedIn':'Naukri'} in the dedicated browser. Please wait...`;
  button.setAttribute('aria-busy','true');
  try{
    const result=await api('/api/browser/connect/'+portal,{method:'POST',signal:AbortSignal.timeout(45000)});
    if(result.state!=='USER_LOGIN_REQUIRED')throw new Error('Login window was not confirmed. Check the dedicated browser before trying again.');
    status.textContent=`${portal==='linkedin'?'LinkedIn':'Naukri'} login tab opened in the dedicated Chrome window. Switch to that window and enter credentials/MFA yourself. Login does not enable direct discovery or automatic applications.`;
  }catch(error){status.className='manual connection-error';status.textContent=`Could not confirm the login tab: ${error.name==='TimeoutError'?'request timed out; check the dedicated browser before retrying':error.message}. No login was verified.`;}
  finally{for(const name of ['linkedin','naukri'])$('connect-'+name).disabled=false;button.removeAttribute('aria-busy');}
});

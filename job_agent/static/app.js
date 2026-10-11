'use strict';
const $ = id => document.getElementById(id);
let statuses = [];
let pollTimer = null;
let searchBackground = null;
let currentPage = 1;
const filterIds=['search','status-filter','mode-filter','score-filter','title-filter','freshness-filter','location_bucket-filter','experience-filter','skills-filter','skill_mode-filter','category-filter','eligibility-filter','seniority-filter','activity-filter','employer-filter','priority-filter','source-filter','kind-filter','sort-filter'];
const saveFilters=()=>sessionStorage.setItem('jobFilters',JSON.stringify(Object.fromEntries(filterIds.map(id=>[id,$(id).value]))));
const restoreFilters=()=>{try{const saved=JSON.parse(sessionStorage.getItem('jobFilters')||'{}');for(const [id,value] of Object.entries(saved))if($(id))$(id).value=value;}catch{sessionStorage.removeItem('jobFilters');}};
const text = (tag, content, className = '') => { const el = document.createElement(tag); el.textContent = content; el.className = className; return el; };
function message(content, error = false) { $('message').textContent = content; $('message').className = error ? 'error' : ''; }
async function api(path, options = {}) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || 'Request failed');
  return data;
}
function statusOptions(select, current) {
  for (const value of statuses) { const option = text('option', value.replaceAll('_', ' ')); option.value = value; option.selected = value === current; select.append(option); }
}
async function refresh() {
  const params = new URLSearchParams({q: $('search').value, min_score: $('score-filter').value, page: currentPage, page_size: 50});
  if ($('status-filter').value) params.set('status', $('status-filter').value);
  if ($('mode-filter').value) params.set('work_mode', $('mode-filter').value);
  for (const name of ['category', 'priority', 'source', 'kind', 'sort', 'eligibility', 'seniority', 'employer', 'activity', 'freshness', 'location_bucket', 'experience', 'skill_mode', 'title']) if ($(name + '-filter').value) params.set(name, $(name + '-filter').value);
  if ($('skills-filter').value) params.set('skills', $('skills-filter').value);
  const [result, overview, events] = await Promise.all([api('/api/jobs?' + params), api('/api/overview'), api('/api/audit?limit=8')]); const jobs=result.items;
  $('total').textContent = overview.total; $('shortlisted').textContent = overview.shortlisted; $('strong').textContent = overview.strong;
  $('result-count').textContent = `${result.total} opportunities match ? showing ${jobs.length}`; $('page-status').textContent=`Page ${result.page} of ${result.pages || 1}`; $('previous-page').disabled=!result.has_previous; $('next-page').disabled=!result.has_next;
  $('jobs').replaceChildren();
  const employers=[...new Set(jobs.map(j=>j.company))].sort(); const currentEmployer=$('employer-filter').value; $('employer-filter').replaceChildren(text('option','All employers')); $('employer-filter').firstChild.value=''; for(const company of employers){const option=text('option',company);option.value=company;option.selected=company===currentEmployer;$('employer-filter').append(option);}
  if (!jobs.length) $('jobs').append(text('div', 'No opportunities here yet. Import a job file or adjust your filters.', 'empty'));
  for (const job of jobs) {
    const card = text('article', '', 'job');
    const top = text('div', '', 'job-top'); const info = text('div', '');
    const heading = text('h3', ''); const link = text('button', job.title); link.addEventListener('click', () => guarded(() => showDetail(job.id))); heading.append(link);
    info.append(heading, text('p', `${job.company} Â· ${job.location}`, 'company'));
    const chips = text('div', '', 'chips'); chips.append(text('span', job.work_mode, 'chip')); if (job.is_sample) chips.append(text('span', 'Fictional sample', 'chip sample'));
    if (job.listing_kind === 'LIVE') { chips.append(text('span', job.activity_status, 'chip live-label'), text('span', `${job.category} ? ${job.priority}`, 'chip'), text('span', `India: ${job.eligibility_state}`, 'chip')); }
    for (const skill of job.skills.slice(0, 4)) chips.append(text('span', skill, 'chip'));
    info.append(chips); if(job.published_at) info.append(text('p','Posted: '+new Date(job.published_at).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'}),'company')); else info.append(text('p','Posting date unknown','company')); if (job.last_seen) info.append(text('p', 'Last seen: ' + new Date(job.last_seen).toLocaleString(), 'company')); const score = text('div', '', 'score'); score.append(text('strong', job.match_score), text('small', 'FIT / 100')); top.append(info, score); card.append(top);
    const actions = text('div', '', 'job-actions'); const shortlist = text('button', job.status === 'SHORTLISTED' ? 'Shortlisted' : 'Shortlist', 'secondary'); shortlist.disabled = job.status === 'SHORTLISTED'; shortlist.addEventListener('click', () => guarded(() => changeStatus(job.id, 'SHORTLISTED')));
    const label = text('label', 'Manual status'); const select = document.createElement('select'); select.setAttribute('aria-label', `Manual status for ${job.title}`); statusOptions(select, job.status);
    select.addEventListener('change', () => guarded(async () => { try { await changeStatus(job.id, select.value); } catch (error) { select.value = job.status; throw error; } })); label.append(select); actions.append(shortlist, label); card.append(actions); $('jobs').append(card);
  }
  $('audit').replaceChildren();
  if (!events.length) $('audit').append(text('p', 'Your activity will appear here.'));
  for (const event of events) { const entry = text('div', '', 'activity'); entry.append(text('strong', event.action.replaceAll('_', ' ')), text('span', JSON.stringify(event.details)), text('time', new Date(event.created_at).toLocaleString())); $('audit').append(entry); }
}
async function changeStatus(id, status) {
  await api(`/api/jobs/${id}/status`, {method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({status})});
  message(`Manual status saved: ${status.replaceAll('_', ' ')}. No application was sent.`); await refresh();
}
async function refreshRecommendations() {
  const params=new URLSearchParams({limit:'25'}); if($('recommendation-eligibility').value)params.set('eligibility',$('recommendation-eligibility').value); if($('recommendation-role').value)params.set('role_family',$('recommendation-role').value);
  const jobs=await api('/api/recommendations?'+params); $('recommendations').replaceChildren(); $('recommendation-status').textContent=`${jobs.length} ranked recommendations. Scores are not hiring probabilities.`;
  for(const job of jobs){const card=text('article','', 'job'); const top=text('div','', 'job-top'); const heading=text('h3',''); const link=text('button',job.title); link.addEventListener('click',()=>guarded(()=>showDetail(job.id))); heading.append(link); top.append(heading,text('strong',`${job.recommendation_score.toFixed(1)}/100`,'score')); const chips=text('div','', 'chips'); chips.append(text('span',job.gate_state==='ELIGIBLE'?'India eligible':'Eligibility unverified','chip'),text('span',job.recommendation_confidence+' evidence','chip'),text('span',job.ai_state,'chip')); const why=job.recommendation_explanation; card.append(top,text('p',`${job.company} · ${job.location}`),chips,text('p',(why.why||[]).join(' ')),text('p',`Matched: ${(why.matched_skills||[]).join(', ')||'None identified'} · Review: ${(why.missing_or_uncertain||[]).join(', ')||'None'}`)); $('recommendations').append(card);}
}
async function showDetail(id) {
  const job = await api(`/api/jobs/${id}`); $('detail-title').textContent = job.title;
  const body = $('detail-body'); body.replaceChildren(text('p', `${job.company} Â· ${job.location} Â· ${job.work_mode}`), text('p', `Fit ${job.match_score}/100 Â· ${job.is_sample ? 'Fictional sample' : job.listing_kind === 'LIVE' ? 'Live public listing' : 'Imported opportunity'}`), text('div', `Status: ${job.status.replaceAll('_', ' ')} Â· Manual tracking. Submission is not verified.`, 'manual'));
  if (job.listing_kind === 'LIVE') body.append(text('p', `Published: ${job.published_at ? new Date(job.published_at).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'}) : 'unknown'} ? First discovered: ${new Date(job.first_seen).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'})} ? Source updated: ${job.source_updated_at ? new Date(job.source_updated_at).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'}) : 'unknown'}`), text('p', `${job.category} ? ${job.priority} ? ${job.seniority_level} ? Match confidence: ${job.match.confidence} ? Activity: ${job.activity_status}`), text('div', `India: ${job.eligibility_state} (${job.eligibility_confidence}) ? ${job.eligibility_explanation} Evidence: ${job.eligibility_evidence}`, 'manual'));
  for (const [heading, values] of [['Matching reasons', job.match.reasons], ['Missing requirements / unknowns', job.match.missing_requirements], ['Potential disqualifiers', job.match.potential_disqualifiers]]) {
    const section = text('section', '', 'detail-section'); section.append(text('h3', heading)); const list = document.createElement('ul'); for (const value of values.length ? values : ['None identified']) list.append(text('li', value)); section.append(list); body.append(section);
  }
  const description = text('section', '', 'detail-section'); description.append(text('h3', 'Description'), text('p', job.description || 'No description supplied.', 'description')); body.append(description);
  const sources = text('section', '', 'detail-section'); sources.append(text('h3', 'Source references'));
  for (const source of job.sources) {
    const row = text('p', `${source.source}${source.source_job_id ? ' Â· ' + source.source_job_id : ''} `);
    if (source.listing_url || source.application_url) { const url = new URL(source.listing_url || source.application_url); if (['http:', 'https:'].includes(url.protocol)) { const anchor = text('a', 'View employer listing (no submission)', 'source-link'); anchor.href = url.href; anchor.target = '_blank'; anchor.rel = 'noopener noreferrer'; row.append(anchor); } }
    sources.append(row);
  }
  body.append(sources); const history = text('section', '', 'detail-section'); history.append(text('h3', 'Status history')); for (const entry of job.history) history.append(text('p', `${entry.status.replaceAll('_', ' ')} Â· ${new Date(entry.created_at).toLocaleString()}`)); body.append(history); $('detail-dialog').showModal();
}
async function guarded(action) { try { await action(); } catch (error) { message(error.message, true); } }
const split = value => value.split(';').map(s => s.trim()).filter(Boolean);
async function initialize() {
  statuses = await api('/api/statuses'); statusOptions($('status-filter'), '');
  const profile = await api('/api/profile'); for (const [id, field] of [['titles', 'target_titles'], ['skills', 'skills'], ['locations', 'locations'], ['exclusions', 'exclusions']]) $('profile-' + id).value = profile[field].join('; ');
  $('profile-experience').value = profile.experience_years ?? ''; for (const checkbox of document.querySelectorAll('[name=profile-mode]')) checkbox.checked = profile.work_modes.includes(checkbox.value);
  searchBackground = await api('/api/search-background'); $('background-total').value = searchBackground.total_years; $('background-backend').value = searchBackground.backend_years; $('background-established').value = searchBackground.established_skills.join('; '); $('background-developing').value = searchBackground.developing_skills.join('; '); $('background-note').textContent = searchBackground.evidence_note;
  const candidate=await api('/api/candidate-profile'); $('candidate-employment').value=candidate.employment_skills.join('; '); $('candidate-projects').value=candidate.project_skills.join('; '); $('candidate-learning').value=candidate.learning_skills.join('; '); $('candidate-locations').value=candidate.preferred_locations.join('; '); $('candidate-years').value=candidate.total_experience_years??''; $('candidate-ai-years').value=candidate.ai_employment_years??''; $('candidate-reviewed').checked=candidate.reviewed; $('resume-status').textContent=candidate.resume_attached?(candidate.resume_reviewed?'Resume reviewed':'Resume attached; facts need review'):'No resume attached';
  await refreshSources(); restoreFilters(); await refreshRecommendations(); const latest = await api('/api/discovery/latest'); if (latest) { renderRun(latest); if (latest.status === 'RUNNING') pollRun(latest.id); }
  await refresh();
}
async function refreshSources() {
  const sources = await api('/api/sources'); const current = $('source-filter').value; $('source-filter').replaceChildren(text('option', 'All sources')); $('source-filter').firstChild.value = '';
  $('source-health').replaceChildren();
  for (const source of sources) {
    const option = text('option', source.company); option.value = source.id; option.selected = source.id === current; $('source-filter').append(option);
    const card = text('article', '', 'source-card'); const label = text('label', ''); const checkbox = document.createElement('input'); checkbox.type = 'checkbox'; checkbox.checked = source.enabled; checkbox.setAttribute('aria-label', `Enable ${source.company}`);
    checkbox.addEventListener('change', () => guarded(async () => { checkbox.disabled = true; try { await api('/api/sources/' + source.id, {method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({enabled: checkbox.checked})}); await refreshSources(); } catch (error) { checkbox.checked = source.enabled; throw error; } finally { checkbox.disabled = false; } }));
    label.append(checkbox, text('span', `${source.company} ? ${source.provider}`)); card.append(label, text('small', `Health: ${source.health}${source.last_error ? ' ? ' + source.last_error : ''}`), text('small', `Verified: ${source.verified ? new Date(source.verified_at).toLocaleString() : 'No'} ? India roles: ${source.india_relevant === null ? 'unknown' : source.india_relevant ? 'present' : 'not observed'}`), text('small', source.verification_evidence || 'No verification evidence'), text('small', 'Last successful scan: ' + (source.last_success ? new Date(source.last_success).toLocaleString() : 'Never')), text('small', 'Next eligible: ' + (source.next_scan_after ? new Date(source.next_scan_after).toLocaleString() : 'Now'))); $('source-health').append(card);
  }
}
function renderRun(run) {
  const m = run.metrics; $('run-discovery').disabled = run.status === 'RUNNING';
  $('discovery-status').textContent = `${run.status} ? New ${m.new_jobs} ? Updated ${m.updated_jobs} ? Unchanged ${m.unchanged_jobs} ? Duplicates ${m.duplicates} ? Failed ${m.failed_sources} ? Requests ${m.requests} ? ${m.response_bytes} bytes ? Eligible ${m.india_eligible_jobs ?? 0} ? Unknown ${m.unknown_eligibility_jobs ?? 0}${run.duration_seconds !== null ? ' ? ' + run.duration_seconds + 's' : ''}`;
}
async function pollRun(id) {
  clearTimeout(pollTimer);
  try { const run = await api('/api/discovery/runs/' + id); renderRun(run); if (run.status === 'RUNNING') { pollTimer = setTimeout(() => pollRun(id), 2000); } else { await Promise.all([refresh(), refreshSources()]); } } catch (error) { $('run-discovery').disabled = false; message(error.message, true); }
}
$('run-discovery').addEventListener('click', () => guarded(async () => { $('run-discovery').disabled = true; $('discovery-status').textContent = 'Starting bounded discoveryâ€¦'; try { const response = await api('/api/discovery/runs', {method: 'POST'}); await pollRun(response.run_id); } catch (error) { $('run-discovery').disabled = false; throw error; } }));
$('background-form').addEventListener('submit', event => { event.preventDefault(); guarded(async () => { searchBackground = await api('/api/search-background', {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({...searchBackground, total_years: Number($('background-total').value), backend_years: Number($('background-backend').value), established_skills: split($('background-established').value), developing_skills: split($('background-developing').value)})}); message('Live search background saved and existing live listings rescored.'); await refresh(); }); });
$('filters').addEventListener('submit', event => { event.preventDefault(); currentPage=1; saveFilters(); guarded(refresh); });
$('previous-page').addEventListener('click',()=>{if(currentPage>1){currentPage--;guarded(refresh);}}); $('next-page').addEventListener('click',()=>{currentPage++;guarded(refresh);});
$('clear-filters').addEventListener('click',()=>{ $('filters').reset(); sessionStorage.removeItem('jobFilters'); $('freshness-filter').value=''; $('experience-filter').value=''; saveFilters(); currentPage=1; guarded(refresh); });
$('reset-preferences').addEventListener('click',()=>{ $('filters').reset(); $('freshness-filter').value='48h'; $('experience-filter').value='5-8'; $('location_bucket-filter').value='DELHI_NCR,GURUGRAM,NOIDA,GREATER_NOIDA,MOHALI,CHANDIGARH,REMOTE_INDIA'; $('sort-filter').value='priority'; saveFilters(); currentPage=1; guarded(refresh); });
$('refresh').addEventListener('click', () => guarded(refresh));
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
    const payload={version:current.version,target_roles:current.target_roles,employment_skills:split($('candidate-employment').value),project_skills:split($('candidate-projects').value),learning_skills:split($('candidate-learning').value),total_experience_years:$('candidate-years').value===''?null:Number($('candidate-years').value),ai_employment_years:$('candidate-ai-years').value===''?null:Number($('candidate-ai-years').value),seniority:current.seniority,preferred_locations:split($('candidate-locations').value),exclusions:current.exclusions,reviewed:$('candidate-reviewed').checked};
    await api('/api/candidate-profile',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}); message('Candidate profile version saved locally. Recommendations refreshed.'); await refreshRecommendations();
  });
});
$('resume-form').addEventListener('submit', event => {
  event.preventDefault(); guarded(async () => {
    const body=new FormData(); body.append('file',$('resume-file').files[0]); await api('/api/candidate-profile/resume',{method:'POST',body}); $('resume-status').textContent='Resume attached locally; review facts before accepting them.'; message('Local resume reference stored. The original resume was not modified.');
  });
});
guarded(initialize);

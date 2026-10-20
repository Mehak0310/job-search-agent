/* Batch-scoped progress, durable answers and a user-initiated completion sound. */
'use strict';
let reviewTimer=null;
let activeReviewBatch=null;
let reviewFailures=0;
let browserRenderVersion=0;
let reviewAudio=null;
const promptedQuestions=new Set();
const observedReviewBatches=new Set();
function armReviewSound(){try{reviewAudio=reviewAudio||new (window.AudioContext||window.webkitAudioContext)();reviewAudio.resume().catch(()=>{});}catch{}}
function batchBeep(){
  if(window.notificationQuiet===true)return false;
  if(!$('batch-sound').checked||!reviewAudio||reviewAudio.state!=='running')return false;
  for(const offset of [0,.25]){const tone=reviewAudio.createOscillator(),volume=reviewAudio.createGain();tone.connect(volume);volume.connect(reviewAudio.destination);tone.frequency.value=offset?880:660;volume.gain.value=.1;tone.start(reviewAudio.currentTime+offset);tone.stop(reviewAudio.currentTime+offset+.18);}
  return true;
}
async function askApplicationAnswers(id){
  const questions=await api('/api/browser/applications/'+id+'/questions');
  if(!questions.length){message('Saved answers already cover these fields, or the remaining controls require agent inspection/manual consent. Refresh progress to synchronize.');return false;}
  $('answer-fields').replaceChildren();$('answer-error').textContent='';$('answer-form').dataset.application=id;
  for(const [index,q] of questions.entries()){
    const group=text('div','','answer-question');const input=q.options.length?document.createElement('select'):document.createElement('textarea');input.id='review-answer-'+index;input.required=true;input.dataset.key=q.key;
    if(q.options.length){const empty=text('option','Choose an answer');empty.value='';input.append(empty);for(const value of q.options){const option=text('option',value);option.value=value;input.append(option);}}
    else{input.rows=3;if(q.max_length>0)input.maxLength=q.max_length;}
    const label=text('label',q.label);label.htmlFor=input.id;group.append(label,text('small',q.instructions||'Saved for this exact question and employer by default.'),input);
    if(!/previous|ever worked|consult|restrict|conflict|sponsor|authoriz/i.test(q.label)){const reuse=document.createElement('input');reuse.type='checkbox';reuse.className='reuse-answer';const reuseLabel=text('label','','history-toggle');reuseLabel.append(reuse,document.createTextNode('Reuse this answer for the same question at other employers'));group.append(reuseLabel);}
    $('answer-fields').append(group);
  }
  if(!$('answer-dialog').open)$('answer-dialog').showModal();return true;
}
$('answer-close').addEventListener('click',()=>$('answer-dialog').close());
$('answer-form').addEventListener('submit',event=>{event.preventDefault();const button=event.target.querySelector('button[type=submit]');button.disabled=true;
  (async()=>{try{const answers=[...$('answer-fields').querySelectorAll('[data-key]')].map(input=>({key:input.dataset.key,value:input.value,reuse:!!input.closest('.answer-question').querySelector('.reuse-answer:checked')}));
    const result=await api('/api/browser/applications/'+$('answer-form').dataset.application+'/answers',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({answers})});
    $('answer-dialog').close();await renderSavedApplicationFacts();message(`Answers saved in profile version ${result.version}. Existing applications are being synchronized.`);await refreshBrowser();reviewTimer=setTimeout(()=>guarded(refreshBrowser),3000);
  }catch(error){$('answer-error').textContent=error.message;}finally{button.disabled=false;}})();
});
async function refreshBrowser(){
 try{await renderBrowserState();reviewFailures=0;}
 catch(error){clearTimeout(reviewTimer);reviewFailures++;$('browser-progress').textContent='Progress connection interrupted; saved application history is preserved. Reconnecting: '+error.message;reviewTimer=setTimeout(()=>refreshBrowser(),Math.min(30000,3000*reviewFailures));}
}
async function renderBrowserState(){
 const renderVersion=++browserRenderVersion;
 clearTimeout(reviewTimer);
 const [rowsResult,progressResult]=await Promise.allSettled([api('/api/browser/applications'+($('browser-history').checked?'?include_history=true':'')),api('/api/browser/progress')]);
 if(rowsResult.status==='rejected')throw rowsResult.reason;
 const rows=rowsResult.value;
 const progress=progressResult.status==='fulfilled'?progressResult.value:{batches:[],operations:[],documents:[],work_active:false};
 if(renderVersion!==browserRenderVersion)return;
 const batches=progress.batches||[];
 if(Object.hasOwn(progress,'active_batch_id'))activeReviewBatch=progress.active_batch_id;
 else if(!activeReviewBatch)activeReviewBatch=(batches.find(b=>['QUEUED','RUNNING'].includes(b.status))||batches[0])?.id;
 const batch=batches.find(b=>b.id===activeReviewBatch);
 $('document-availability').textContent=(progress.documents||[]).map(d=>`${d.name}: ${d.available?'approved PDF available':'file unavailable; please attach the approved PDF'}`).join(' | ');
 $('browser-progress').textContent=progressResult.status==='rejected'?'Saved applications are shown; live batch progress is temporarily unavailable. '+progressResult.reason:batch?`Current review batch: ${batch.processed} of ${batch.total} processed; ${batch.ready} ready for your review; ${batch.needs_answers} need answers; ${batch.agent_checks} need agent checks; ${batch.submitted||0} marked submitted (see history); ${batch.preparing||0} preparing.`:rows.length?`${rows.length} tracked applications. ${rows.filter(r=>r.state==='PREPARING').length} preparing.`:'No browser forms prepared yet.';
 const busy=progress.work_active||batch&&['QUEUED','RUNNING'].includes(batch.status);if(busy&&batch)observedReviewBatches.add(batch.id);
 const operation=(progress.operations||[]).find(w=>['QUEUED','RUNNING'].includes(w.state));
 if(operation)$('browser-progress').textContent+=` ${operation.phase}. Last heartbeat: ${formatCheckpoint(operation.heartbeat_at)}.`;
 if(operation?.kind==='SYNC')$('browser-progress').textContent=`Synchronizing existing applications: ${operation.cursor} of ${operation.application_ids.length} inspected. ${operation.phase}. Last heartbeat: ${formatCheckpoint(operation.heartbeat_at)}.`;
 $('browser-batch').disabled=!!busy;
 const expanded=new Set([...$('browser-applications').querySelectorAll('article.job')].filter(c=>c.querySelector('.review-tools')?.open).map(c=>c.dataset.applicationId));const olderOpen=!!$('browser-applications').querySelector('.older-applications[open]');
 $('browser-applications').replaceChildren();
 const priorityIds=new Set(operation?.application_ids||[]);
 const ordered=activeReviewBatch||priorityIds.size?[...rows].sort((a,b)=>(Number(priorityIds.has(b.id))*2+Number(b.batch_id===activeReviewBatch))-(Number(priorityIds.has(a.id))*2+Number(a.batch_id===activeReviewBatch))):rows;
 let older=null,olderList=null;
 if(ordered.length>5){older=document.createElement('details');older.className='older-applications';older.open=olderOpen;older.append(text('summary',`Other tracked applications (${ordered.length-5})`));olderList=text('div','','older-application-list');older.append(olderList);}
 for(const [index,row] of ordered.entries()){
   const card=text('article','','job');card.dataset.applicationId=row.id;const unavailable=['vacancy_http_404','vacancy_http_410','vacancy_closed'].includes(row.inspection.error_code);
   for(const resolution of row.answer_resolutions||[])card.append(text('p',`${resolution.label}: ${resolution.state.replaceAll('_',' ')} - ${resolution.explanation}`));
   const outcome=row.application_outcome||row.state;
   const submitted=['USER_REPORTED_SUBMITTED','SUBMISSION_CONFIRMED'].includes(outcome);
   const unsafeReady=!submitted&&row.state==='READY_FOR_USER_REVIEW'&&!row.ready_for_user_review;
   const submittedLabel=outcome==='USER_REPORTED_SUBMITTED'?'Marked submitted manually; not independently verified':'Submission confirmed by recorded employer evidence';
   const stateLabel=submitted?(row.submission_label||row.status_message||submittedLabel):unsafeReady?'Prepared form retained; eligibility must be reverified':row.status_message||(row.state==='SESSION_LOST'?'Browser session lost; application history preserved':row.state.replaceAll('_',' '));
   const visibleState=submitted?outcome:unsafeReady?'NEEDS_VERIFICATION':row.state;
   card.append(text('h3',`${row.company} | ${row.title}`),text('strong',unavailable?'No longer accepting applications':stateLabel,'chip review-state state-'+visibleState));
   card.append(text('p',`Eligibility: ${row.eligibility_status||'UNKNOWN'}`,'eligibility-status'));
   if(row.eligibility_reasons?.length)card.append(bulletSection('Eligibility blockers',row.eligibility_reasons));
   const vacancy=applicationLink(row.source_url||row.vacancy_url,'Source vacancy');if(vacancy)card.append(vacancy);
   if(row.connection_status)card.append(text('p',`Browser session: ${row.connection_status.toLowerCase()} | ${row.completed_fields||0} fields completed | ${row.phase||'Awaiting inspection'}`));
   if(row.next_action)card.append(text('p','Next safe action: '+row.next_action,'manual'));
   if(row.retry_condition)card.append(text('p',row.retry_condition,'manual'));
   if(row.inspection.error_code)card.append(text('p','Last inspection blocker: '+row.inspection.error_code,'manual'));
   if(row.session_health==='LOST'&&!row.retry_condition)card.append(text('p','Next action: restore the dedicated Chrome session and refresh progress. Check existing employer progress before reconstruction; do not repeat uploads.','manual'));
   card.append(text('p',`Last form check: ${formatCheckpoint(row.inspection.verified_at)}`));
   if(row.state==='PREPARING')card.append(text('p',row.inspection.stage||'Opening and inspecting the application...'));
   const personal=row.missing.filter(m=>!/^Agent action:|\.pdf:|ATS form|Saved tab|Last Name currently/i.test(m));
   if(personal.length)card.append(bulletSection('Fields being resolved',personal));
   if(row.checks.length)card.append(bulletSection('Employer research (handled by the agent)',row.checks.map(readableCheck)));
   card.append(bulletSection('Documents',row.documents.map(d=>`${d.name}: ${d.verified?'filename and acceptance verified':'being reconciled; no duplicate upload'}`),'No verified upload recorded.'));
   const actions=text('div','','job-actions');
   if(row.target_id&&!unavailable){const review=text('button','Switch to application tab','secondary');review.addEventListener('click',()=>guarded(async()=>{review.disabled=true;message('Connecting to the saved employer tab...');try{const result=await api('/api/browser/applications/'+row.id+'/switch',{method:'POST'});message(result.state==='SESSION_LOST'?'Saved employer tab is unavailable. Restore the dedicated Chrome session and refresh progress. Review employer progress before reconstruction; do not repeat uploads.':'Application tab selected.');await refreshBrowser();}finally{review.disabled=false;}}));actions.append(review);}
   if(row.state==='NEEDS_USER_ANSWER'){const answers=text('button','Answer missing questions','secondary');answers.addEventListener('click',()=>guarded(()=>askApplicationAnswers(row.id)));actions.append(answers);}
   card.append(actions);
   const details=document.createElement('details');details.className='review-tools';details.open=expanded.has(row.id);details.append(text('summary','Troubleshooting and manual history'));
   const tools=text('div','','job-actions');const link=applicationLink(row.url,'Direct application');if(link&&!unavailable)tools.append(link);
   for(const [label,action] of [['Reinspect form / confirmation','inspect'],['Fill newly supported answers','resume']]){const button=text('button',label,'secondary');button.disabled=action==='resume'&&(!row.ready_for_user_review&&row.eligibility_status!=='PASS'||submitted||['SESSION_LOST','USER_REPORTED_SUBMITTED','SUBMISSION_CONFIRMED'].includes(row.state));button.addEventListener('click',()=>guarded(async()=>{await api('/api/browser/applications/'+row.id+'/'+action,{method:'POST'});message(action==='inspect'?'Form inspection completed.':'Preparation started.');await refreshBrowser();}));tools.append(button);}
   if(row.state==='SESSION_LOST'){const rebuild=text('button','Reconstruct after progress review','secondary');rebuild.addEventListener('click',()=>guarded(async()=>{if(!window.confirm('Have you checked existing employer progress and application history, and confirmed reconstruction will not duplicate an application?'))return;await api('/api/browser/batches',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({job_ids:[row.job_id],limit:1,reconstruct_after_progress_review:true})});await refreshBrowser();}));tools.append(rebuild);}
   const reported=text('button','I submitted this application','secondary');reported.disabled=submitted;reported.addEventListener('click',()=>guarded(async()=>{await api('/api/browser/applications/'+row.id+'/reported-submitted',{method:'POST'});message('Recorded as user-reported; no confirmed submission evidence was inferred.');await Promise.all([refreshBrowser(),refreshM3(),refreshRecommendations(),refresh()]);}));tools.append(reported);if(row.job_id)tools.append(unavailableButton(row.job_id));details.append(tools);card.append(details);(index<5?$('browser-applications'):olderList).append(card);
 }
 if(older)$('browser-applications').append(older);
 if(typeof loadPriority==='function')loadPriority();
 if(busy||rows.some(r=>r.state==='PREPARING'))reviewTimer=setTimeout(()=>refreshBrowser(),document.hidden?15000:3000);
 if(batch&&!busy&&['REVIEW','ERROR'].includes(batch.status)){
   const key='batch-notified:'+batch.id+':'+batch.finished_at;
   const summary=`Review batch processed: ${batch.processed}/${batch.total}. ${batch.ready} ready for review, ${batch.needs_answers} need answers, ${batch.agent_checks} need agent checks, ${batch.submitted||0} marked submitted (history). No automatic submission.`;
   $('batch-completion').textContent=summary;
   if(observedReviewBatches.has(batch.id)&&!sessionStorage.getItem(key)){sessionStorage.setItem(key,'yes');const sounded=batchBeep();message(summary+(sounded?'':' Sound is unavailable or disabled; this banner is your notification.'));
     const pending=rows.find(r=>r.batch_id===batch.id&&r.state==='NEEDS_USER_ANSWER'&&!promptedQuestions.has(r.id));if(pending&&!$('answer-dialog').open){promptedQuestions.add(pending.id);if(window.askBatchAnswers)await window.askBatchAnswers(batch.id);else await askApplicationAnswers(pending.id);}
   }
 }
}
$('browser-batch').addEventListener('click',()=>{armReviewSound();$('browser-batch').disabled=true;guarded(async()=>{try{const result=await api('/api/browser/batches',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({limit:5})});if(result.selected){activeReviewBatch=result.batch_id;observedReviewBatches.add(result.batch_id);}message(result.selected?`Started ${result.selected} application tabs for review. No automatic submission.`:'No new suitable jobs to prepare. Applied, unavailable and already-prepared jobs are excluded.');await refreshBrowser();}catch(error){$('browser-batch').disabled=false;throw error;}});});
$('browser-history').addEventListener('change',()=>guarded(refreshBrowser));
$('browser-refresh').addEventListener('click',()=>guarded(async()=>{message('Synchronizing actual browser forms and saved answers...');await api('/api/browser/sync',{method:'POST'});await refreshBrowser();reviewTimer=setTimeout(()=>guarded(refreshBrowser),3000);}));
$('batch-sound').addEventListener('change',()=>{if($('batch-sound').checked)armReviewSound();});
async function renderSavedApplicationFacts(){const saved=await api('/api/browser/saved-facts');const wrap=text('div','','command-table-wrap'),table=text('table','','command-table'),head=text('thead'),heading=text('tr');for(const title of ['Field','Approved value','Provenance']){const th=text('th',title);th.scope='col';heading.append(th);}head.append(heading);const body=text('tbody');for(const fact of saved.facts){const row=text('tr','','saved-fact-row');for(const value of [fact.label,fact.value,fact.source+' | profile '+saved.profile_version])row.append(text('td',value));body.append(row);}table.append(head,body);wrap.append(table);$('saved-application-facts').replaceChildren(wrap);}
window.addEventListener('online',()=>refreshBrowser());
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshBrowser();});
sectionLoad('browser-panel',refreshBrowser);
sectionLoad('professional-profile',renderSavedApplicationFacts);
guarded(async()=>{await initialize();window.workspaceInitialized=true;if((!location.hash||location.hash==='#opportunities-panel')&&($('source-filter').value==='gmail'||$('kind-filter').value==='EMAIL')){location.hash='email-leads-panel';navigateWorkspace('email-leads-panel');}});

/* Durable notification presentation; piggybacks existing progress refresh only. */
'use strict';
(() => {
 const button=text('button','Notifications','secondary');button.id='notification-center-button';document.querySelector('body>header').append(button);
 const dialog=document.createElement('dialog');dialog.id='notification-center';dialog.setAttribute('aria-label','Batch notifications');
 let editingBatch=null;
 const close=text('button','Close notifications','secondary');close.onclick=()=>{editingBatch=null;dialog.close();};dialog.addEventListener('cancel',()=>{editingBatch=null;});
 const list=text('div'),status=text('p','Notifications load with application progress.');status.setAttribute('role','status');
 const sound=document.createElement('input');sound.type='checkbox';const soundLabel=text('label','Enable sound while this page is open ');soundLabel.prepend(sound);
 const desktop=text('button','Enable desktop notifications','secondary');
 dialog.append(text('h2','Batch notifications'),close,status,soundLabel,desktop,list);document.body.append(dialog);
 const seen=new Set();let preferences={sound:false,desktop:false,quiet_start:22,quiet_end:8};
 const save=()=>api('/api/notifications/preferences',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(preferences)});
 sound.onchange=()=>guarded(async()=>{armReviewSound();preferences.sound=sound.checked;$('batch-sound').checked=sound.checked;await save();});
 $('batch-sound').addEventListener('change',()=>guarded(async()=>{preferences.sound=$('batch-sound').checked;sound.checked=preferences.sound;await save();}));
 desktop.onclick=()=>guarded(async()=>{if(!('Notification' in window)){status.textContent='Desktop notifications are unavailable in this browser.';return;}preferences.desktop=(await Notification.requestPermission())==='granted';await save();status.textContent=preferences.desktop?'Desktop notifications enabled while this page runs.':'Desktop permission was not granted.';});
 async function refreshNotifications(){
  try{
   const result=await api('/api/notifications');preferences=result.preferences;window.notificationQuiet=result.quiet;sound.checked=Boolean(preferences.sound);$('batch-sound').checked=sound.checked;if(editingBatch)return;list.replaceChildren();
   button.textContent='Notifications ('+result.items.filter(n=>n.attention).length+')';
   status.textContent=result.quiet?'Quiet hours active (Asia/Calcutta).':'Sound requires a user gesture and an open page; background delivery is not guaranteed.';
   for(const row of result.items){
    const card=text('article','','command-document');card.append(text('h3',row.kind.replaceAll('_',' ')),text('p',row.payload.message||''));
    if(row.resolved)card.append(text('small','Resolved; retained for reference.'));
    else for(const [label,minutes] of [['Acknowledge',0],['Snooze 15 minutes',15]]){const action=text('button',label,'secondary');action.onclick=()=>guarded(async()=>{await api('/api/notifications/'+row.id+'/acknowledge',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision:row.revision,snooze_minutes:minutes})});await refreshNotifications();});card.append(action);}
    if(row.kind==='MISSING_INFORMATION'&&!row.resolved){const answer=text('button','Answer batch questions','secondary');answer.onclick=()=>guarded(()=>questions(row.batch_id));card.append(answer);}
    list.append(card);const key=row.id+':'+row.revision;
    if(row.attention&&!seen.has(key)){seen.add(key);if(row.audible){const previous=$('batch-sound').checked;$('batch-sound').checked=true;batchBeep();$('batch-sound').checked=previous;}if(preferences.desktop&&!result.quiet&&'Notification' in window&&Notification.permission==='granted')new Notification('Job application review',{body:row.payload.message,tag:row.id});}
   }
   if(!result.items.length)list.append(text('p','No new batch notifications.'));
  }catch(error){status.textContent='Notification service unavailable: '+error.message;}
 }
 async function questions(batch){
  const result=await api('/api/browser/batches/'+batch+'/questions');if(!result.items.length){editingBatch=null;status.textContent='No unresolved batch questions remain. Refresh application progress for agent-owned checks.';return;}editingBatch=batch;const form=document.createElement('form');form.append(text('h3','Missing information across this batch'),text('p','Approved facts were checked first. Answers apply only to the listed employers.'));
  for(const q of result.items){const group=text('label',q.label+' ('+[...new Set(q.targets.map(t=>t.company))].join(', ')+')');const input=document.createElement(q.options.length?'select':'textarea');input.required=true;input.dataset.questionId=q.id;if(q.max_length>0)input.maxLength=q.max_length;if(q.options.length){const blank=text('option','Choose an answer');blank.value='';input.append(blank);for(const value of q.options){const option=text('option',value);option.value=value;input.append(option);}}group.append(input);form.append(group);}
  const error=text('p');error.setAttribute('role','alert');const submit=text('button','Save answers and resume');submit.type='submit';form.append(error,submit);list.replaceChildren(form);
  form.onsubmit=async event=>{event.preventDefault();submit.disabled=true;try{const answers=[...form.querySelectorAll('[data-question-id]')].map(n=>({id:n.dataset.questionId,value:n.value}));const saved=await api('/api/browser/batches/'+batch+'/answers',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({answers})});editingBatch=null;status.textContent='Answers saved. '+saved.resume_state;await refreshBrowser();await refreshNotifications();}catch(e){error.textContent=e.message;}finally{submit.disabled=false;}};
 }
 button.onclick=()=>{armReviewSound();dialog.showModal();refreshNotifications();};
 window.askBatchAnswers=async batch=>{if(!dialog.open)dialog.showModal();await questions(batch);};
 const original=refreshBrowser;refreshBrowser=async function(...args){const result=await original(...args);await refreshNotifications();return result;};
 const planning=text('details');planning.append(text('summary','Plan up to three future batches'));
 const planList=text('div'),planButton=text('button','Build pending batch plans','secondary');planning.append(text('p','Plans do not open browser tabs or reserve active work. Eligibility and priority are checked again when preparing.'),planButton,planList);$('priority-panel').append(planning);
 async function showPlans(){const result=await api('/api/orchestration/plans');planList.replaceChildren();for(const row of result.items.filter(r=>r.state==='PLANNED')){const card=text('article','','command-document');card.append(text('p',row.job_ids.length+' pending jobs'));const prepare=text('button','Prepare this batch','secondary');prepare.onclick=()=>guarded(async()=>{prepare.disabled=true;try{await api('/api/orchestration/plans/'+row.id+'/prepare',{method:'POST'});await refreshBrowser();await showPlans();}finally{prepare.disabled=false;}});card.append(prepare);planList.append(card);}if(!planList.children.length)planList.append(text('p','No eligible future batches planned.'));}
 planButton.onclick=()=>guarded(async()=>{await api('/api/orchestration/plans',{method:'POST'});await showPlans();});planning.ontoggle=()=>{if(planning.open)guarded(showPlans);};
 const schedules=$('command-schedules');const disabled=text('details');disabled.append(text('summary','Persistent schedule plans (disabled)'));
 const scheduleForm=document.createElement('form'),stage=document.createElement('select');stage.setAttribute('aria-label','Schedule stage');for(const value of ['DISCOVERY','GMAIL_INTAKE','VERIFICATION','PREPARATION','NOTIFICATIONS']){const option=text('option',value);stage.append(option);}const savePlan=text('button','Save disabled hourly plan','secondary');savePlan.type='submit';const scheduleStatus=text('p','No schedule is installed or activated. Existing ChatGPT automation stages remain unchanged.');scheduleForm.append(stage,savePlan);disabled.append(scheduleStatus,scheduleForm);schedules.append(disabled);
 scheduleForm.onsubmit=event=>{event.preventDefault();guarded(async()=>{await api('/api/orchestration/schedules',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({stage:stage.value,interval_seconds:3600,next_run:new Date(Date.now()+3600000).toISOString()})});scheduleStatus.textContent='Disabled plan saved. Execution requires separate approval; no schedule was activated.';});};
 refreshNotifications();
})();

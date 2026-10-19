import {test,expect,open,job,view} from './portal-fixture';

test('resolved batch alerts retain history without stale answer or acknowledgement actions',async({page,harness})=>{
 harness.replies.set('GET /api/notifications',{body:{items:[{id:'resolved',batch_id:'batch',revision:2,resolved:true,attention:false,audible:false,kind:'MISSING_INFORMATION',payload:{message:'Resolved; this batch condition no longer requires action.'}}],preferences:{sound:false,desktop:false},quiet:false}});
 await open(page,'home-panel');await page.getByRole('button',{name:'Notifications (0)',exact:true}).click();
 const center=page.getByRole('dialog',{name:'Batch notifications'});
 await expect(center).toContainText('Resolved; retained for reference.');
 await expect(center.getByRole('button',{name:'Answer batch questions'})).toHaveCount(0);
 await expect(center.getByRole('button',{name:'Acknowledge',exact:true})).toHaveCount(0);
 expect(harness.writes).toEqual([]);
});

test('unknown requirements override stale packet readiness on job cards',async({page,harness})=>{
 harness.replies.set('GET /api/jobs',{body:{items:[{...job,card:{...view,readiness:'READY_FOR_PORTAL_REVIEW',requirement_assessment:{state:'UNKNOWN',reasons:['Unsupported mandatory clause']}}}],total:1,page:1,pages:1,has_next:false,has_previous:false}});
 await open(page,'opportunities-panel');
 await expect(page.locator('#jobs .chips')).toContainText('Requirements: UNKNOWN');
 await expect(page.locator('#jobs .chips')).not.toContainText('Ready for portal review');
});

test('batch notification acknowledgement and snooze use exact revision',async({page,harness})=>{
 harness.replies.set('GET /api/notifications',{body:{items:[{id:'note',revision:2,attention:true,audible:false,kind:'READY',payload:{message:'Two forms ready'}}],preferences:{sound:false,desktop:false},quiet:false}});
 harness.replies.set('POST /api/notifications/note/acknowledge',{body:{saved:true}});
 await open(page,'home-panel');await page.getByRole('button',{name:'Notifications (1)',exact:true}).click();
 const center=page.getByRole('dialog',{name:'Batch notifications'});await expect(center).toContainText('Two forms ready');
 await center.getByRole('button',{name:'Snooze 15 minutes'}).click();
 await expect.poll(()=>harness.writes.length).toBe(1);expect(harness.writes[0].body).toEqual({revision:2,snooze_minutes:15});
 await center.getByRole('button',{name:'Acknowledge',exact:true}).click();await expect.poll(()=>harness.writes.length).toBe(2);
 expect(harness.writes[1].body).toEqual({revision:2,snooze_minutes:0});
});

test('consolidated answers survive progress refresh and save exact scope',async({page,harness})=>{
 const id='a'.repeat(64);
 harness.replies.set('GET /api/notifications',{body:{items:[{id:'question-note',batch_id:'batch',revision:1,attention:true,audible:false,kind:'MISSING_INFORMATION',payload:{message:'One question remains'}}],preferences:{sound:false,desktop:false},quiet:false}});
 harness.replies.set('GET /api/browser/batches/batch/questions',{body:{items:[{id,label:'Years in unfamiliar domain',options:[],max_length:100,targets:[{company:'Example',application_id:'fixture-browser'}]}]}});
 harness.replies.set('POST /api/browser/batches/batch/answers',{body:{resume_state:'QUEUED_AFTER_ACTIVE_WORK'}});
 await open(page,'home-panel');await page.getByRole('button',{name:'Notifications (1)',exact:true}).click();
 await page.getByRole('button',{name:'Answer batch questions',exact:true}).click();
 const answer=page.getByLabel('Years in unfamiliar domain (Example)');await answer.fill('No professional experience');
 await page.evaluate(async()=>{await (window as any).refreshBrowser();});
 await expect(answer).toHaveValue('No professional experience');
 await page.getByRole('button',{name:'Save answers and resume',exact:true}).click();
 await expect.poll(()=>harness.writes.some(w=>w.path==='/api/browser/batches/batch/answers')).toBe(true);
 expect(harness.writes.find(w=>w.path.endsWith('/batch/answers'))?.body).toEqual({answers:[{id,value:'No professional experience'}]});
});

test('future batch planning and disabled schedule controls dispatch supported operations',async({page,harness})=>{
 const plans={items:[{id:'plan',state:'PLANNED',job_ids:['fixture-job']}],max_preplanned:3};
 harness.replies.set('GET /api/orchestration/plans',{body:plans});
 harness.replies.set('POST /api/orchestration/plans',{body:plans});
 harness.replies.set('POST /api/orchestration/plans/plan/prepare',{body:{batch_id:'planned-batch',selected:0}});
 harness.replies.set('POST /api/orchestration/schedules',{body:{id:'disabled',enabled:false}});
 await open(page,'browser-panel');await page.locator('.command-subnav').getByRole('link',{name:'Priority Queue',exact:true}).click();await page.getByText('Plan up to three future batches',{exact:true}).click();
 await page.getByRole('button',{name:'Build pending batch plans',exact:true}).click();
 await expect(page.getByRole('button',{name:'Prepare this batch',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Prepare this batch',exact:true}).click();
 await expect.poll(()=>harness.writes.some(w=>w.path==='/api/orchestration/plans/plan/prepare')).toBe(true);
 await page.getByRole('tab',{name:'Sources & Activity',exact:true}).click();await page.locator('.command-subnav').getByRole('link',{name:'Schedules',exact:true}).click();
 await page.getByText('Persistent schedule plans (disabled)',{exact:true}).click();
 await page.getByLabel('Schedule stage',{exact:true}).selectOption('VERIFICATION');
 await page.getByRole('button',{name:'Save disabled hourly plan',exact:true}).click();
 await expect(page.getByText('Disabled plan saved. Execution requires separate approval; no schedule was activated.',{exact:true})).toBeVisible();
 expect(harness.writes.find(w=>w.path==='/api/orchestration/schedules')?.body.stage).toBe('VERIFICATION');
 expect(harness.writes.some(w=>w.path.endsWith('/activate'))).toBe(false);
});

const sections:[string,string,string[]][]=[
 ['Home','home-panel',['Overview','My Actions','Recent Activity']],
 ['Find Jobs','opportunities-panel',['Best Matches','Shortlisted','All Jobs','Needs Verification']],
 ['Applications','browser-panel',['Priority Queue','Preparing','Ready to Review','Applied','Follow-ups']],
 ['Inbox & Drafts','email-leads-panel',['Recruiter Inbox','Job Alerts','Draft Approvals','Draft History']],
 ['Sources & Activity','discovery-panel',['Source Health','Run History','Schedules','Verification Backlog']],
 ['My Profile','professional-profile',['Career Facts','Documents','Saved Answers','Preferences']],
];
for(const [title,root,views] of sections)test('command center routes: '+title,async({page,harness})=>{
 await open(page,root);await expect(page.locator('#command-title')).toHaveText(title);
 await expect(page.getByRole('tab')).toHaveCount(6);
 for(const view of views){await page.locator('.command-subnav').getByRole('link',{name:view,exact:true}).click();await expect(page.locator('.command-subnav [aria-current=page]')).toHaveText(view);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);}
 await page.reload();await expect(page.locator('.command-subnav [aria-current=page]')).toHaveText(views.at(-1)!);
 expect(harness.writes).toHaveLength(0);
});
for(const width of [390,768,1440])test('command center screenshots and responsive shell '+width,async({page,harness},info)=>{
 await page.setViewportSize({width,height:1000});await open(page,'home-panel');
 for(const [title,root] of sections){await page.getByRole('tab',{name:title,exact:true}).click();await expect(page.locator('#command-title')).toHaveText(title);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.screenshot({path:info.outputPath(root+'-'+width+'.png')});}
 expect(harness.writes).toHaveLength(0);
});
test('sidebar persistence, keyboard routing and Settings outside six tabs',async({page,harness})=>{
 await open(page,'home-panel');await page.getByRole('button',{name:'Collapse sidebar'}).click();await expect(page.locator('body')).toHaveClass(/sidebar-collapsed/);await page.reload();await expect(page.locator('body')).toHaveClass(/sidebar-collapsed/);
 await page.getByRole('tab',{name:'Home',exact:true}).focus();await page.keyboard.press('ArrowDown');await expect(page.locator('#command-title')).toHaveText('Find Jobs');await page.getByRole('button',{name:'Settings',exact:true}).click();await expect(page.locator('#tools-panel')).toBeVisible();await expect(page.getByRole('tab')).toHaveCount(6);
});
test('job detail actions and nonmodal packet drawer remain accessible',async({page,harness})=>{
 await open(page);await expect(page.locator('#command-job-detail')).toContainText('Angular matches the vacancy');await expect(page.locator('#command-job-detail .vacancy-link').first()).toHaveAttribute('href','https://example.com/jobs/123');
 await page.locator('#command-job-detail').getByRole('button',{name:'Review or edit application'}).click();await expect(page.locator('#detail-dialog')).toBeVisible();await expect(page.locator('#detail-dialog')).toHaveAttribute('aria-modal','false');await page.keyboard.press('Escape');await expect(page.locator('#detail-dialog')).not.toBeVisible();expect(harness.writes).toHaveLength(0);
});
test('source failure is local and retained view clearly says stale',async({page,harness})=>{
 harness.replies.set('GET /api/sources',{status:503,body:{detail:'source fixture unavailable'}});await open(page,'browser-panel');await expect(page.locator('#browser-progress')).not.toBeEmpty();await page.getByRole('tab',{name:'Sources & Activity'}).click();await expect(page.locator('#view-checkpoint')).toContainText('source fixture unavailable');await expect(page.locator('#discovery-panel .section-error')).toContainText('source fixture unavailable');
});
test('recruiter view separates received actions from automated alerts',async({page,harness})=>{
 harness.replies.set('GET /api/inbox/messages',{body:{items:[{message_id:'interview',subject:'Interview tomorrow',sender:'Hiring team',category:'INTERVIEW_REQUEST',deadline:'2026-10-20',reason:'Explicit interview request',received_at:'2026-10-19',gmail_url:'https://mail.google.com/mail/u/0/#inbox/interview'},{message_id:'alert',subject:'500 jobs today',category:'AUTOMATED_JOB_ALERT',received_at:'2026-10-19'}]}});
 await open(page,'email-leads-panel');await expect(page.locator('#command-recruiter-inbox')).toContainText('Interview tomorrow');await expect(page.locator('#command-recruiter-inbox')).not.toContainText('500 jobs today');await page.getByRole('button',{name:'Read recruiter conversation'}).click();await expect(page.getByRole('link',{name:'Read original Gmail conversation'})).toHaveAttribute('href',/inbox\/interview$/);expect(harness.writes).toHaveLength(0);
});
test('verification view uses canonical cross-gate state rather than India eligibility alone',async({page,harness})=>{
 harness.replies.set('GET /api/priority-queue',{body:{pending:1,verification:1,items:[{job_id:'fixture-job',state:'VERIFICATION',fit:85,eligibility:'UNKNOWN',reason:'Mandatory evidence incomplete',source:'fixture'},{job_id:'unprepared-job',state:'PENDING',fit:80,eligibility:'PASS',source:'fixture'}]}});
 await open(page,'opportunities-panel/needs-verification');await expect(page.locator('#jobs>article.job')).toHaveCount(1);await expect(page.locator('#jobs')).toContainText('Frontend fixture');await expect(page.locator('#result-count')).toContainText('1 needing verification on this page');expect(harness.writes).toHaveLength(0);
});
test('simultaneous priority reads share one request without caching later refreshes',async({page,harness})=>{
 let requests=0;page.on('request',r=>{if(new URL(r.url()).pathname==='/api/priority-queue')requests++;});
 harness.replies.set('GET /api/priority-queue',{delay:500,body:{pending:0,verification:0,items:[]}});
 await open(page,'home-panel');await page.evaluate(async()=>{await (window as any).api('/api/priority-queue');});const before=requests;
 await page.evaluate(async()=>{await Promise.all([1,2,3].map(()=>(window as any).api('/api/priority-queue')));});expect(requests).toBe(before+1);
 await page.getByRole('button',{name:'Refresh view',exact:true}).click();await expect.poll(()=>requests).toBe(before+2);expect(harness.writes).toHaveLength(0);
});
test('opening Home does not announce an old completed batch as newly processed',async({page,harness})=>{
 harness.replies.set('GET /api/browser/progress',{body:{active_batch_id:'old',work_active:false,documents:[],operations:[],batches:[{id:'old',status:'REVIEW',processed:5,total:5,ready:0,needs_answers:0,agent_checks:5,finished_at:'2026-10-18T00:00:00Z'}]}});
 await open(page,'home-panel');await expect(page.locator('#batch-completion')).toContainText('5/5');await expect(page.locator('#message')).not.toContainText('Review batch processed');await expect(page.locator('#answer-dialog')).not.toBeVisible();expect(harness.writes).toHaveLength(0);
});

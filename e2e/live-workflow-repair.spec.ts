import { test, expect, open } from './fixtures';

const application={id:'repair-app',job_id:'repair-job',batch_id:'repair-batch',company:'Fixture Employer',title:'Frontend fixture',state:'SESSION_LOST',session_health:'LOST',target_id:'stale-target',url:'https://example.com/jobs/123',inspection:{},missing:[],checks:[],documents:[]};

test('five application summary accounts for manually submitted fifth application',async({page,harness})=>{
  harness.replies.set('GET /api/browser/applications',{body:[application]});
  harness.replies.set('GET /api/browser/progress',{body:{active_batch_id:'repair-batch',batches:[{id:'repair-batch',status:'REVIEW',processed:5,total:5,ready:0,needs_answers:0,agent_checks:4,submitted:1,preparing:0}],operations:[],documents:[],work_active:false}});
  await open(page,'browser-panel');
  await expect(page.locator('#browser-progress')).toContainText('4 need agent checks; 1 marked submitted (see history); 0 preparing');
});

test('tab switching shows pending feedback and actionable bounded failure',async({page,harness})=>{
  harness.replies.set('GET /api/browser/applications',{body:[application]});
  harness.replies.set('POST /api/browser/applications/repair-app/switch',{delay:400,status:409,body:{detail:'Browser connection timed out. Check the dedicated Chrome window, then retry Switch to application tab. Saved progress is preserved.'}});
  await open(page,'browser-panel');
  const button=page.getByRole('button',{name:'Switch to application tab',exact:true});
  await button.click();
  await expect(button).toBeDisabled();
  await expect(page.locator('#message')).toContainText('Connecting to the saved employer tab');
  await expect(page.locator('#message')).toContainText('Browser connection timed out');
  await expect(button).toBeEnabled();
  expect(harness.writes.filter(r=>r.path.endsWith('/switch'))).toHaveLength(1);
});

test('progress failure does not blank saved applications or erase an answer in progress',async({page,harness})=>{
  harness.replies.set('GET /api/browser/applications',{body:[{...application,state:'NEEDS_USER_ANSWER',eligibility_status:'UNKNOWN',eligibility_reasons:['Headcount evidence is stale.'],source_url:'https://example.com/jobs/123',connection_status:'INSPECTION_REQUIRED',next_action:'Resolve eligibility evidence blockers.',missing:['Years in B2B SaaS'],ready_for_user_review:false}]});
  harness.replies.set('GET /api/browser/progress',{status:503,body:{detail:'Synthetic progress outage'}});
  harness.replies.set('GET /api/sources',{status:503,body:{detail:'Synthetic Sources outage'}});
  harness.replies.set('GET /api/browser/applications/repair-app/questions',{body:[{key:'question:fixture',label:'Years in B2B SaaS',instructions:'Synthetic fixture question',options:[],max_length:40}]});
  await open(page,'browser-panel');
  await expect(page.locator('#browser-applications')).toContainText('Fixture Employer | Frontend fixture');
  await expect(page.locator('#browser-progress')).toContainText('Saved applications are shown');
  await expect(page.locator('#browser-applications')).toContainText('Eligibility: UNKNOWN');
  await page.getByRole('button',{name:'Answer missing questions',exact:true}).click();
  const answer=page.getByLabel('Years in B2B SaaS',{exact:true});
  await answer.fill('Synthetic answer in progress');
  await page.evaluate(async()=>{await (window as any).refreshBrowser();});
  await expect(answer).toHaveValue('Synthetic answer in progress');
  expect(harness.writes).toHaveLength(0);
});

test('stale eligibility cannot place a previously prepared form in Ready to Review',async({page,harness})=>{
  harness.replies.set('GET /api/browser/applications',{body:[{...application,state:'READY_FOR_USER_REVIEW',session_health:'CONNECTED',target_id:'fixture-target',eligibility_status:'UNKNOWN',eligibility_reasons:['Headcount evidence is stale.'],source_url:'https://example.com/jobs/123',connection_status:'CONNECTED',next_action:'Resolve eligibility evidence blockers.',missing:[],checks:[],documents:[],ready_for_user_review:false}]});
  harness.replies.set('GET /api/browser/progress',{body:{active_batch_id:'repair-batch',batches:[],operations:[],documents:[],work_active:false}});
  await open(page,'browser-panel');
  const card=page.locator('#browser-applications article.job');
  await expect(card).toContainText('Prepared form retained; eligibility must be reverified');
  await expect(card).toContainText('Eligibility: UNKNOWN');
  await expect(card.locator('.state-READY_FOR_USER_REVIEW')).toHaveCount(0);
});

test('manual submission dominates a legacy ready state and blocks duplicate actions',async({page,harness})=>{
  harness.replies.set('GET /api/browser/applications',{body:[{...application,state:'READY_FOR_USER_REVIEW',application_outcome:'USER_REPORTED_SUBMITTED',submission_label:'Marked submitted manually; not independently verified',status_message:'Marked submitted manually; not independently verified',eligibility_status:'PASS',connection_status:'CONNECTED',ready_for_user_review:false}]});
  harness.replies.set('GET /api/browser/progress',{body:{active_batch_id:'repair-batch',batches:[],operations:[],documents:[],work_active:false}});
  await open(page,'browser-panel');
  await page.getByRole('link',{name:'Applied',exact:true}).click();
  const card=page.locator('#browser-applications article.job');
  await expect(card).toContainText('Marked submitted manually; not independently verified');
  await expect(card.locator('.state-USER_REPORTED_SUBMITTED')).toHaveCount(1);
  await expect(card.locator('.state-READY_FOR_USER_REVIEW')).toHaveCount(0);
  await card.locator('details.review-tools').evaluate((details:HTMLDetailsElement)=>details.open=true);
  await expect(card.getByRole('button',{name:'Fill newly supported answers'})).toBeDisabled();
  await expect(card.getByRole('button',{name:'I submitted this application'})).toBeDisabled();
  expect(harness.writes).toHaveLength(0);
  await page.getByRole('link',{name:'Ready to Review',exact:true}).click();
  await expect(page.locator('#browser-applications article.job')).toBeHidden();
});

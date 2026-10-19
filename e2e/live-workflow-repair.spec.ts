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

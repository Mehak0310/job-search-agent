import { test, expect, open } from './fixtures';
const packet={packet_id:'fixture',job_id:'job-fixture',title:'Frontend fixture',company:'Example',missing_information:[],fit_summary:['Angular matches the role'],gaps:[],application_url:'https://example.com/jobs/123'};
const application={id:'application-fixture',job_id:'job-fixture',company:'Example',title:'Frontend fixture',state:'NEEDS_USER_ANSWER',url:packet.application_url,inspection:{},missing:[],checks:[],documents:[]};

test('reported application disappears from active review and stays in history after reload',async({page,harness})=>{
  harness.replies.set('GET /api/m3/packets',{body:[packet]});
  harness.replies.set('GET /api/browser/applications',{body:[application]});
  harness.replies.set('GET /api/browser/progress',{body:{batches:[],operations:[],documents:[],work_active:false}});
  let applied=false;
  await page.route('**/api/browser/applications**',async route=>{
    if(route.request().method()==='POST'){
      applied=true;harness.replies.set('GET /api/m3/packets',{body:[]});return route.fulfill({json:{state:'USER_REPORTED_SUBMITTED',submission_verified:false}});
    }
    const history=new URL(route.request().url()).searchParams.get('include_history');
    return route.fulfill({json:applied?(history?[{...application,state:'USER_REPORTED_SUBMITTED'}]:[]):[application]});
  });
  await open(page,'browser-panel');await page.locator('#browser-applications .review-tools summary').first().click();await page.getByRole('button',{name:'I submitted this application',exact:true}).click();
  await expect(page.locator('#browser-applications .job')).toHaveCount(0);await expect(page.locator('.packet-card')).toHaveCount(0);
  await page.reload();await expect(page.locator('.packet-card')).toHaveCount(0);await expect(page.locator('#browser-progress')).toContainText('No browser forms');
  await page.locator('#browser-history').check();await expect(page.locator('#browser-applications')).toContainText('Marked submitted manually; not independently verified');await page.locator('#browser-applications .review-tools summary').click();await expect(page.getByRole('button',{name:'I submitted this application'})).toBeDisabled();
});

test('unavailable link report removes packet and survives refresh',async({page,harness})=>{
  harness.replies.set('GET /api/m3/packets',{body:[packet]});
  await page.route('**/api/jobs/job-fixture/review-dismissal',async r=>{
    harness.replies.set('GET /api/m3/packets',{body:[]});return r.fulfill({json:{removed_from_review:true,history_preserved:true}});
  });
  await open(page,'m3-panel');await page.locator('.packet-card').getByRole('button',{name:'Remove unavailable job'}).click();
  await expect(page.locator('.packet-card')).toHaveCount(0);await expect(page.locator('#message')).toContainText('History is preserved');await page.reload();await expect(page.locator('.packet-card')).toHaveCount(0);
});

test('a transient failed dismissal keeps the job visible and shows an error',async({page,harness})=>{
  harness.replies.set('GET /api/m3/packets',{body:[packet]});harness.replies.set('POST /api/jobs/job-fixture/review-dismissal',{status:503,body:{detail:'Temporary local error'}});
  await open(page,'m3-panel');await page.locator('.packet-card').getByRole('button',{name:'Remove unavailable job'}).click();await expect(page.locator('#message')).toContainText('Temporary local error');await expect(page.locator('.packet-card')).toHaveCount(1);
});

test('rendered interface has no broken separators or encoding artifacts',async({page,harness})=>{
  await open(page,'browser-panel');await page.locator('#browser-history').check();const body=await page.locator('body').innerText();
  expect(body).not.toMatch(/[\u00c3\u00c2\ufffd]/);expect(body).not.toContain(' ? ');expect(body).not.toContain('Loading your workspace?');
});

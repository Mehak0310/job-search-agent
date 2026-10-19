import { test, expect, open } from './fixtures';

test.describe('Portal connections: visible feedback and safe failure',()=>{
  for(const portal of ['linkedin','naukri']){
    test(`${portal}: pending, duplicate prevention and successful handoff`,async({page,harness})=>{
      harness.replies.set('POST /api/browser/connect/'+portal,{body:{state:'USER_LOGIN_REQUIRED'},delay:500});
      await open(page,'browser-panel');await page.getByText('LinkedIn / Naukri connections',{exact:true}).click();
      const button=page.locator('#connect-'+portal);await button.click();
      await expect(button).toBeDisabled();await expect(page.locator('#connection-status')).toContainText('Please wait');
      await expect(page.locator('#connection-status')).toContainText('login tab opened');
      await expect(button).toBeEnabled();expect(harness.writes).toHaveLength(1);
    });
    test(`${portal}: errors remain next to clicked control`,async({page,harness})=>{
      harness.replies.set('POST /api/browser/connect/'+portal,{status:409,body:{detail:'browser_session_busy'}});
      await open(page,'browser-panel');await page.getByText('LinkedIn / Naukri connections',{exact:true}).click();await page.locator('#connect-'+portal).click();
      await expect(page.locator('#connection-status')).toContainText('browser_session_busy');
      await expect(page.locator('#connection-status')).toContainText('No login was verified');await expect(page.locator('#connect-'+portal)).toBeEnabled();
    });
  }
  test('network interruption is visible and retry is available',async({page,harness})=>{
    await open(page,'browser-panel');await page.route('**/api/browser/connect/linkedin',r=>r.abort());
    await page.getByText('LinkedIn / Naukri connections',{exact:true}).click();await page.locator('#connect-linkedin').click();
    await expect(page.locator('#connection-status')).toContainText('Could not confirm');await expect(page.locator('#connect-linkedin')).toBeEnabled();
  });
});

test.describe('Filters, navigation and empty/error states',()=>{
  test('filter values persist after refresh and can be cleared',async({page,harness})=>{
    await open(page,'opportunities-panel');await page.locator('#search').fill('Angular');await page.locator('#filters button[type=submit]').click();
    await page.reload();await expect(page.locator('#search')).toHaveValue('Angular');
    await page.locator('#clear-filters').click();await expect(page.locator('#search')).toHaveValue('');
    expect(harness.writes).toHaveLength(0);
  });
  test('reset restores approved search defaults',async({page,harness})=>{
    await open(page,'opportunities-panel');await page.locator('#clear-filters').click();await page.locator('#reset-preferences').click();
    await expect(page.locator('#freshness-filter')).toHaveValue('48h');await expect(page.locator('#experience-filter')).toHaveValue('5-8');
  });
  test('email lead shortcut sets exact source filter',async({page,harness})=>{
    await open(page,'opportunities-panel');await page.locator('#email-leads').click();await expect(page.locator('#email-leads-panel')).toBeVisible();await expect(page).toHaveURL(/#email-leads-panel\/job-alerts$/);
  });
  test('read failure produces visible feedback',async({page,harness})=>{
    await open(page,'opportunities-panel');await page.route('**/api/jobs?**',r=>r.fulfill({status:503,json:{detail:'Temporary local read failure'}}));await page.locator('#refresh').click();
    await expect(page.locator('#message')).toContainText('Temporary local read failure');
  });
});

test.describe('Application preparation and exports',()=>{
  test('queue preparation gives outcome without a real write',async({page,harness})=>{
    harness.replies.set('POST /api/m3/packets/prepare',{body:{prepared:2,unchanged:1,failed:[]}});await open(page,'m3-panel');await page.locator('#prepare-applications').click();
    await expect(page.locator('#message')).toContainText('2 prepared, 1 unchanged, 0 failed');expect(harness.writes[0].path).toBe('/api/m3/packets/prepare');
  });
  test('export reports returned path and upload state',async({page,harness})=>{
    harness.replies.set('POST /api/m3/export',{body:{path:'data/test-review.xlsx',packets:2,upload_status:'local_only'}});await open(page,'m3-panel');await page.locator('#export-applications').click();
    await expect(page.locator('#message')).toContainText('data/test-review.xlsx');
  });
  test('packet editor saves a version and closes',async({page,harness})=>{
    await open(page,'m3-panel');const card=page.locator('.packet-card').first();test.skip(await card.count()===0,'No existing packets to inspect');
    await card.getByRole('button',{name:'Edit prepared text'}).click();await expect(page.locator('#detail-dialog')).toBeVisible();
    await page.getByLabel('Subject',{exact:true}).fill('Reviewed local test subject');
    await page.route('**/api/m3/packets/*',async r=>r.request().method()==='PUT'?r.fulfill({json:{saved:true}}):r.continue());
    await page.getByRole('button',{name:'Save new local version'}).click();await expect(page.locator('#detail-dialog')).not.toBeVisible();await expect(page.locator('#message')).toContainText('Saved a new local packet version');
  });
  test('packet edit failure keeps edited text for recovery',async({page,harness})=>{
    await open(page,'m3-panel');const card=page.locator('.packet-card').first();test.skip(await card.count()===0,'No existing packets');await card.getByRole('button',{name:'Edit prepared text'}).click();
    await page.getByLabel('Subject',{exact:true}).fill('Keep this unsaved edit');await page.getByRole('button',{name:'Save new local version'}).click();
    await expect(page.locator('#message')).toContainText('Test blocked');await expect(page.getByLabel('Subject',{exact:true})).toHaveValue('Keep this unsaved edit');await page.locator('#close-dialog').click();
  });
});

test.describe('Browser review controls',()=>{
  test('batch preparation is bounded to five',async({page,harness})=>{
    harness.replies.set('POST /api/browser/batches',{body:{selected:2}});await open(page,'browser-panel');await page.locator('#browser-batch').click();
    await expect(page.locator('#message')).toContainText('Started 2');expect(harness.writes[0].body.limit).toBe(5);
  });
  test('browser progress refresh requests bounded synchronization',async({page,harness})=>{await open(page,'browser-panel');harness.replies.set('POST /api/browser/sync',{body:{state:'SYNCHRONIZING'}});await page.locator('#browser-refresh').click();await expect.poll(()=>harness.writes.length).toBe(1);});
  for(const [label,suffix] of [['Switch to application tab','switch'],['Reinspect form / confirmation','inspect'],['Fill newly supported answers','resume'],['I submitted this application','reported-submitted']]){
    test(label+' dispatches the specific operation',async({page,harness})=>{
      harness.replies.set('GET /api/browser/applications',{body:[{id:'fixture',job_id:'job-fixture',company:'Example',title:'Frontend engineer',state:'NEEDS_USER_ANSWER',url:'https://example.com/job',target_id:'tab',inspection:{},missing:['Surname'],checks:['payroll'],documents:[]}]});
      harness.replies.set('POST /api/browser/applications/fixture/'+suffix,{body:{state:'NEEDS_USER_ANSWER'}});
      await open(page,'browser-panel');await page.locator('#browser-applications .review-tools summary').first().click();await page.locator('#browser-applications').getByRole('button',{name:label,exact:true}).click();
      await expect.poll(()=>harness.writes.length).toBe(1);expect(harness.writes[0].path).toBe('/api/browser/applications/fixture/'+suffix);
    });
  }
});

test.describe('Local data forms: writes intercepted',()=>{
  test('import displays report and re-enables button',async({page,harness})=>{
    harness.replies.set('POST /api/import',{body:{created:1,duplicates:0,invalid:0}});await open(page,'tools-panel');
    await page.locator('#import-file').setInputFiles({name:'fixture.json',mimeType:'application/json',buffer:Buffer.from('[]')});await page.locator('#import-form button').click();await expect(page.locator('#import-result')).toContainText('"created": 1');await expect(page.locator('#import-form button')).toBeEnabled();
  });
  test('oversize import fails before dispatch',async({page,harness})=>{
    await open(page,'tools-panel');await page.locator('#import-file').setInputFiles({name:'large.json',mimeType:'application/json',buffer:Buffer.alloc(2*1024*1024+1)});await page.locator('#import-form button').click();await expect(page.locator('#message')).toContainText('2 MiB');expect(harness.writes).toHaveLength(0);
  });
  for(const [form,path,label] of [['profile-form','/api/profile','Matching preferences'],['background-form','/api/search-background','Live search background and skill evidence'],['candidate-form','/api/candidate-profile','']]){
    test(form+' saves through its API',async({page,harness})=>{
      harness.replies.set('PUT '+path,{body:{total_years:7,backend_years:3,established_skills:[],developing_skills:[]}});await open(page,'professional-profile');
      if(label)await page.locator('.command-subnav').getByRole('link',{name:'Preferences',exact:true}).click();await page.locator('#'+form+' button').click();
      await expect.poll(()=>harness.writes.some(w=>w.path===path)).toBe(true);await expect(page.locator('#message')).toContainText('saved');
    });
  }
  test('resume reference replacement sends only chosen fixture',async({page,harness})=>{
    harness.replies.set('POST /api/candidate-profile/resume',{body:{resume_attached:true}});await open(page,'professional-profile/documents');await page.getByText('Resume reference and explicit local parsing',{exact:true}).click();await page.locator('#resume-file').setInputFiles({name:'fixture.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF-1.4 fixture')});await page.locator('#resume-form button').click();await expect(page.locator('#message')).toContainText('Local resume reference stored');
  });
  test('local parsing is explicit and reports proposal count',async({page,harness})=>{
    harness.replies.set('POST /api/candidate-profile/resume/parse',{body:{proposals:3}});await open(page,'professional-profile/documents');await page.getByText('Resume reference and explicit local parsing',{exact:true}).click();expect(harness.writes).toHaveLength(0);await page.locator('#parse-resume').click();await expect(page.locator('#message')).toContainText('3 facts');
  });
});

test.describe('Responsive presentation and keyboard access',()=>{
  for(const width of [390,768,1365])test('viewport '+width,async({page,harness})=>{
    await page.setViewportSize({width,height:900});await open(page,'browser-panel');expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.getByText('LinkedIn / Naukri connections',{exact:true}).focus();await page.keyboard.press('Enter');await expect(page.locator('#connect-linkedin')).toBeVisible();
  });
});


test.describe('Discovery, source configuration and review safeguards',()=>{
  test('discovery start failure re-enables control',async({page,harness})=>{
    harness.replies.set('POST /api/discovery/runs',{status:409,body:{detail:'run_already_active'}});await open(page,'discovery-panel');await page.locator('#run-discovery').click();
    await expect(page.locator('#message')).toContainText('run_already_active');await expect(page.locator('#run-discovery')).toBeEnabled();
  });
  test('bounded discovery completion renders counts',async({page,harness})=>{
    harness.replies.set('POST /api/discovery/runs',{body:{run_id:'fixture-run'}});
    harness.replies.set('GET /api/discovery/runs/fixture-run',{body:{status:'COMPLETED',duration_seconds:1,metrics:{new_jobs:2,updated_jobs:1,unchanged_jobs:3,duplicates:0,failed_sources:0,requests:1,response_bytes:100}}});
    await open(page,'discovery-panel');await page.locator('#run-discovery').click();await expect(page.locator('#discovery-status')).toContainText('COMPLETED');await expect(page.locator('#run-discovery')).toBeEnabled();
  });
  test('source-toggle failure restores its original selection',async({page,harness})=>{
    await open(page,'discovery-panel');await page.getByText('Source enable controls and retained evidence',{exact:true}).click();const checkbox=page.locator('#source-health input[type=checkbox]').first();const checked=await checkbox.isChecked();await checkbox.click();await expect(page.locator('#message')).toContainText('Test blocked');await expect(checkbox).toBeEnabled();expect(await checkbox.isChecked()).toBe(checked);
  });
  test('recommendation refresh calls configured operation',async({page,harness})=>{
    harness.replies.set('POST /api/recommendations/refresh',{body:{jobs_scored:2,cache_hit_rate:1,llm_calls:0}});await open(page,'recommended-panel');await page.locator('#refresh-recommendations').click();await expect.poll(()=>harness.writes.length).toBe(1);expect(harness.writes[0].path).toBe('/api/recommendations/refresh');
  });
  test('recommendation filters reach query string',async({page,harness})=>{
    await open(page,'recommended-panel');const request=page.waitForRequest(r=>r.url().includes('/api/recommendations?')&&r.url().includes('eligibility=UNKNOWN'));await page.locator('#recommendation-eligibility').selectOption('UNKNOWN');expect((await request).method()).toBe('GET');
  });
  test('empty opportunities show a useful explanation',async({page,harness})=>{
    harness.replies.set('GET /api/jobs',{body:{items:[],total:0,page:1,pages:1,has_previous:false,has_next:false}});await open(page,'opportunities-panel');await expect(page.locator('#jobs')).toContainText('No jobs match these filters');await expect(page.locator('#next-page')).toBeDisabled();await expect(page.locator('#previous-page')).toBeDisabled();
  });
  test('pagination requests next page and can go back',async({page,harness})=>{
    harness.replies.set('GET /api/jobs',{body:{items:[],total:100,page:1,pages:2,has_previous:false,has_next:true}});await open(page,'opportunities-panel');
    harness.replies.set('GET /api/jobs',{body:{items:[],total:100,page:2,pages:2,has_previous:true,has_next:false}});await page.locator('#next-page').click();await expect(page.locator('#page-status')).toHaveText('Page 2 of 2');
    harness.replies.set('GET /api/jobs',{body:{items:[],total:100,page:1,pages:2,has_previous:false,has_next:true}});await page.locator('#previous-page').click();await expect(page.locator('#page-status')).toHaveText('Page 1 of 2');
  });
  test('session-lost reconstruction cancel performs no write',async({page,harness})=>{
    harness.replies.set('GET /api/browser/applications',{body:[{id:'fixture',job_id:'job-fixture',company:'Example',title:'Frontend',state:'SESSION_LOST',url:'https://example.com/job',inspection:{},missing:[],checks:[],documents:[]}]});await open(page,'browser-panel');
    page.once('dialog',d=>d.dismiss());await page.locator('.review-tools summary').first().click();await page.getByRole('button',{name:'Reconstruct after progress review'}).click();expect(harness.writes).toHaveLength(0);
  });
  test('session-lost reconstruction requires explicit confirmation',async({page,harness})=>{
    harness.replies.set('GET /api/browser/applications',{body:[{id:'fixture',job_id:'job-fixture',company:'Example',title:'Frontend',state:'SESSION_LOST',url:'https://example.com/job',inspection:{},missing:[],checks:[],documents:[]}]});harness.replies.set('POST /api/browser/batches',{body:{selected:1}});await open(page,'browser-panel');
    page.once('dialog',d=>d.accept());await page.locator('.review-tools summary').first().click();await page.getByRole('button',{name:'Reconstruct after progress review'}).click();await expect.poll(()=>harness.writes.length).toBe(1);expect(harness.writes[0].body.reconstruct_after_progress_review).toBe(true);
  });
  test('already-reported submission control stays disabled',async({page,harness})=>{
    harness.replies.set('GET /api/browser/applications',{body:[{id:'fixture',company:'Example',title:'Frontend',state:'USER_REPORTED_SUBMITTED',url:'https://example.com/job',inspection:{},missing:[],checks:[],documents:[]}]});await open(page,'browser-panel/applied');await page.locator('#browser-applications .review-tools summary').click();await expect(page.getByRole('button',{name:'I submitted this application'})).toBeDisabled();expect(harness.writes).toHaveLength(0);
  });
  for(const action of ['Accept fact','Reject'])test('explicit fact decision: '+action,async({page,harness})=>{
    harness.replies.set('GET /api/candidate-profile/facts',{body:[{id:'fixture-fact',value:'Fixture Python',status:'PENDING',source_ref:'fixture',confidence:1,category:'skills',extraction_id:'fixture-extraction'}]});harness.replies.set('PATCH /api/candidate-profile/facts/fixture-fact',{body:{saved:true}});await open(page,'professional-profile/documents');await page.getByText('Resume reference and explicit local parsing',{exact:true}).click();expect(harness.writes).toHaveLength(0);await page.locator('#fact-proposals').getByRole('button',{name:action,exact:true}).click();await expect.poll(()=>harness.writes.length).toBe(1);expect(harness.writes[0].body.action).toBe(action==='Reject'?'REJECTED':'ACCEPTED');
  });
  test('untrusted packet text is rendered without HTML execution',async({page,harness})=>{
    harness.replies.set('GET /api/m3/packets',{body:[{packet_id:'fixture',title:'<img src=x onerror=alert(1)>',company:'Example',missing_information:[],fit_summary:['<script>alert(1)</script>'],gaps:[],application_url:'javascript:alert(1)'}]});await open(page,'m3-panel');const card=page.locator('.packet-card').first();await expect(card).toContainText('<script>alert(1)</script>');expect(await card.locator('script,img').count()).toBe(0);await expect(card.getByText('Application link unavailable')).toBeVisible();
  });
});

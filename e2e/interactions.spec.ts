import { test, expect, open, job, view, browserRow } from './portal-fixture';

const filters:[string,string,string][]=[
 ['search','Angular','q'],['title-filter','Frontend','title'],['status-filter','NEW','status'],['mode-filter','hybrid','work_mode'],['score-filter','70','min_score'],['freshness-filter','7d','freshness'],['location_bucket-filter','NOIDA','location_bucket'],['experience-filter','3-5','experience'],['skills-filter','Angular','skills'],['skill_mode-filter','all','skill_mode'],['category-filter','FRONTEND','category'],['eligibility-filter','UNKNOWN','eligibility'],['seniority-filter','SENIOR','seniority'],['activity-filter','ACTIVE','activity'],['employer-filter','Example','employer'],['priority-filter','P1','priority'],['source-filter','fixture-source','source'],['kind-filter','IMPORTED','kind'],['sort-filter','score_desc','sort']];
for(const [id,value,param] of filters)test('filter control: '+id,async({page,harness})=>{
 await open(page);const input=page.locator('#'+id);if(await input.evaluate(e=>e.tagName)==='SELECT')await input.selectOption(value);else await input.fill(value);
 const request=page.waitForRequest(r=>new URL(r.url()).pathname==='/api/jobs'&&new URL(r.url()).searchParams.get(param)===value);
 await page.getByRole('button',{name:'Apply filters',exact:true}).click();expect(new URL((await request).url()).searchParams.get(param)).toBe(value);expect(harness.writes).toHaveLength(0);
});

test('shortlist dispatches tracking status and shows feedback',async({page,harness})=>{
 await open(page);harness.replies.set('PATCH /api/jobs/fixture-job/status',{body:{...job,status:'SHORTLISTED'}});
 await page.locator('#command-job-detail').getByRole('button',{name:'Shortlist',exact:true}).click();await expect(page.locator('#message')).toContainText('SHORTLISTED');expect(harness.writes[0].body.status).toBe('SHORTLISTED');
});
test('manual status failure restores previous selection',async({page,harness})=>{
 await open(page);const select=page.getByRole('combobox',{name:'Manual status for Frontend fixture'});await select.selectOption('SUBMITTED');await expect(page.locator('#message')).toContainText('Test blocked');await expect(select).toHaveValue('NEW');
});
test('manual status success dispatches tracking only',async({page,harness})=>{
 harness.replies.set('PATCH /api/jobs/fixture-job/status',{body:{...job,status:'SUBMITTED'}});await open(page);await page.getByRole('combobox',{name:'Manual status for Frontend fixture'}).selectOption('SUBMITTED');await expect(page.locator('#message')).toContainText('No application was sent');expect(harness.writes[0].body.status).toBe('SUBMITTED');
});
test('inline prepared text disclosure opens and closes',async({page,harness})=>{
 await open(page);const details=page.locator('#command-job-detail .prepared-inline');await details.locator('summary').click();await expect(details.getByText('Role-specific email',{exact:true})).toBeVisible();await details.locator('summary').click();await expect(details.getByText('Role-specific email',{exact:true})).not.toBeVisible();
});
test('opportunity edit opens scoped packet and Escape closes modal',async({page,harness})=>{
 await open(page);await page.locator('#command-job-detail').getByRole('button',{name:'Review or edit application'}).click();await expect(page.getByLabel('Subject',{exact:true})).toHaveValue(view.subject);await page.keyboard.press('Escape');await expect(page.locator('#detail-dialog')).not.toBeVisible();
});
test('recommendation heading opens job details and Close restores page',async({page,harness})=>{
 await open(page,'recommended-panel');await page.locator('#recommendations').getByRole('button',{name:job.title,exact:true}).click();await expect(page.locator('#detail-body')).toContainText('Build Angular components');await page.locator('#close-dialog').click();await expect(page.locator('#detail-dialog')).not.toBeVisible();
});
test('prepare text dispatches the exact job key',async({page,harness})=>{
 harness.replies.set('POST /api/m3/packets/job/fixture-key',{body:{prepared:true}});await open(page);await page.locator('#jobs>.job').nth(1).getByRole('button',{name:'View role details'}).click();await page.getByRole('button',{name:'Prepare application text',exact:true}).click();await expect(page.locator('#message')).toContainText('Application text prepared locally');expect(harness.writes[0].path).toBe('/api/m3/packets/job/fixture-key');
});
test('Gmail preview button creates only the exact local approval preview',async({page,harness})=>{
 harness.replies.set('POST /api/m3/packets/fixture-packet/draft-preview',{body:{preview_id:'a'.repeat(64),recipient:'hiring@example.com',recipient_evidence:{source_url:'https://example.com/team'},company:'Example',title:'Frontend fixture',eligibility:'UNKNOWN',subject:'Exact subject',text:'Exact body',attachment_policy:'Manual approved resume only',blockers:[],live_creation_enabled:false}});await open(page);await page.getByRole('button',{name:'Preview Gmail draft',exact:true}).click();await expect(page.locator('#draft-dialog')).toBeVisible();await expect(page.locator('#draft-preview-body')).toContainText('Exact body');expect(harness.writes[0].path).toBe('/api/m3/packets/fixture-packet/draft-preview');expect(harness.writes).toHaveLength(1);
});
test('prepare one browser application scopes the batch to that job',async({page,harness})=>{
 harness.replies.set('POST /api/browser/batches',{body:{selected:1}});await open(page);await page.locator('#command-job-detail').getByRole('button',{name:'Prepare browser application',exact:true}).click();await expect(page.locator('#message')).toContainText('Browser preparation started');expect(harness.writes[0].body).toEqual({job_ids:[job.id],limit:1});
});
test('opportunity switch shows lost-session guidance',async({page,harness})=>{
 harness.replies.set('POST /api/browser/applications/fixture-browser/switch',{body:{state:'SESSION_LOST'}});await open(page);await page.locator('#command-job-detail').getByRole('button',{name:'Switch to application tab'}).click();await expect(page.locator('#message')).toContainText('Saved application tab is unavailable');
});
test('empty browser batch explains why no new tabs opened',async({page,harness})=>{
 harness.replies.set('POST /api/browser/batches',{body:{selected:0}});await open(page,'browser-panel');await page.locator('#browser-batch').click();await expect(page.locator('#message')).toContainText('No new suitable jobs');
});
test('source toggle sends exact enable preference',async({page,harness})=>{
 harness.replies.set('PATCH /api/sources/fixture-source',{body:{enabled:false}});await open(page,'discovery-panel');await page.getByText('Source enable controls and retained evidence',{exact:true}).click();await page.getByRole('checkbox',{name:'Enable Example'}).uncheck();await expect.poll(()=>harness.writes.length).toBe(1);expect(harness.writes[0].body).toEqual({enabled:false});
});
test('role-family recommendation filter dispatches exact family',async({page,harness})=>{
 await open(page,'recommended-panel');const request=page.waitForRequest(r=>new URL(r.url()).pathname==='/api/recommendations'&&new URL(r.url()).searchParams.get('role_family')==='FRONTEND');await page.locator('#recommendation-role').selectOption('FRONTEND');await request;
});

for(const name of ['Matching preferences','Professional profile and resume evidence','Live search background and skill evidence','Configured source coverage and blockers','LinkedIn / Naukri connections','Evidence and technical details'])test('disclosure toggles: '+name,async({page,harness})=>{
 await open(page,name==='Configured source coverage and blockers'?'discovery-panel/verification-backlog':name==='LinkedIn / Naukri connections'?'browser-panel':['Matching preferences','Live search background and skill evidence'].includes(name)?'professional-profile/preferences':name==='Evidence and technical details'?'professional-profile/documents':'professional-profile');if(name==='Evidence and technical details')await page.getByText('Resume reference and explicit local parsing',{exact:true}).click();const summary=page.locator('summary').filter({hasText:name}).first();const details=summary.locator('..');const before=await details.getAttribute('open');await summary.click();expect(await details.getAttribute('open')===null).toBe(before!==null);await summary.click();expect(await details.getAttribute('open')===null).toBe(before===null);
});

const destinations:[string,string][]=[['.packet-card a','https://example.com/jobs/123'],['#jobs .vacancy-link','https://example.com/jobs/123'],['#command-job-detail .check-row a','https://example.com/evidence'],['#recommendations a','https://example.com/jobs/123'],['#browser-applications a','https://example.com/jobs/123']];
for(const [selector,url] of destinations)test('external link dispatches safely: '+selector,async({page,harness})=>{
 await open(page,selector.startsWith('.packet')?'m3-panel':selector.startsWith('#browser')?'browser-panel':selector.startsWith('#recommendations')?'recommended-panel':'opportunities-panel');if(selector.startsWith('#browser'))await page.locator('#browser-applications .review-tools summary').first().click();const link=page.locator(selector).first();await expect(link).toHaveAttribute('href',url);await expect(link).toHaveAttribute('rel','noopener noreferrer');
 const popupPromise=page.waitForEvent('popup');await link.click();const popup=await popupPromise;await expect(popup).toHaveURL(url);await expect(popup.locator('body')).toContainText('External navigation intercepted');await popup.close();expect(harness.writes).toHaveLength(0);
});
test('source-reference link in details opens an intercepted tab',async({page,harness})=>{
 await open(page,'recommended-panel');await page.locator('#recommendations').getByRole('button',{name:job.title,exact:true}).click();const popupPromise=page.waitForEvent('popup');await page.locator('#detail-body a').click();const popup=await popupPromise;await expect(popup).toHaveURL(view.vacancy_url);await popup.close();await page.locator('#close-dialog').click();
});
for(const [label,target] of [['Home','home-panel'],['Applications','browser-panel'],['Inbox & Drafts','email-leads-panel'],['Find Jobs','opportunities-panel'],['My Profile','professional-profile'],['Sources & Activity','discovery-panel']])test('section navigation: '+label,async({page,harness})=>{
 await open(page);await page.getByRole('tablist',{name:'Workspace sections'}).getByRole('tab',{name:label,exact:true}).click();await expect(page).toHaveURL(new RegExp('#'+target+'$'));await expect(page.locator('#'+target)).toBeInViewport();
});
test('skip link is reachable with keyboard',async({page,harness})=>{
 await open(page);await page.keyboard.press('Tab');await expect(page.getByRole('link',{name:'Skip to opportunities'})).toBeFocused();await page.keyboard.press('Enter');await expect(page).toHaveURL(/#opportunities-panel$/);
});
test('unsafe external links are not rendered as anchors',async({page,harness})=>{
 harness.replies.set('GET /api/jobs',{body:{items:[{...job,card:{...view,vacancy_url:'javascript:alert(1)',employer_checks:[{label:'Unsafe',state:'Unknown',detail:'Needs review',owner:'Research',evidence_url:'javascript:alert(1)'}]}}],total:1,page:1,pages:1}});harness.replies.set('GET /api/browser/applications',{body:[{...browserRow,url:'javascript:alert(1)'}]});await open(page);expect(await page.locator('a[href^="javascript:"]').count()).toBe(0);await expect(page.locator('#jobs')).toContainText('Specific vacancy link unavailable');
});


test('employer filter persists when a search returns no rows',async({page,harness})=>{
 await open(page);await page.locator('#employer-filter').selectOption('Example');harness.replies.set('GET /api/jobs',{body:{items:[],total:0,page:1,pages:1,has_next:false,has_previous:false}});await page.getByRole('button',{name:'Apply filters',exact:true}).click();await expect(page.locator('#jobs')).toContainText('No jobs match these filters');await expect(page.locator('#employer-filter')).toHaveValue('Example');
});

test('malformed and credential-bearing source links never break job detail',async({page,harness})=>{
 await open(page,'recommended-panel');
 for(const url of ['not a URL','https://user:secret@example.com/job','javascript:alert(1)']){
  harness.replies.set('GET /api/jobs/'+job.id,{body:{...job,sources:[{source:'fixture',listing_url:url,application_url:url}]}});
  await page.locator('#recommendations').getByRole('button',{name:job.title,exact:true}).click();await expect(page.locator('#detail-dialog')).toBeVisible();await expect(page.locator('#detail-body')).toContainText('Listing link unavailable');expect(await page.locator('#detail-body a').count()).toBe(0);await page.locator('#close-dialog').click();
 }
});

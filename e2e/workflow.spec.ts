import {test,expect,open,browserRow} from './portal-fixture';

test('application review shows five cards and retains older forms in a disclosure',async({page,harness})=>{
 harness.replies.set('GET /api/browser/applications',{body:Array.from({length:6},(_,i)=>({...browserRow,id:'review-'+i,title:'Role '+i}))});
 await open(page,'browser-panel');await expect(page.locator('#browser-applications>.job')).toHaveCount(5);
 await expect(page.getByRole('heading',{name:/Role 5/})).not.toBeVisible();
 await page.getByText('Other tracked applications (1)',{exact:true}).click();await expect(page.getByRole('heading',{name:/Role 5/})).toBeVisible();
 await page.getByText('Other tracked applications (1)',{exact:true}).click();await expect(page.getByRole('heading',{name:/Role 5/})).not.toBeVisible();
});

test('SPA tabs show only their related panels and browser back restores view',async({page,harness})=>{
 await open(page);await expect(page.locator('#opportunities-panel')).toBeVisible();await expect(page.locator('#browser-panel')).not.toBeVisible();
 await page.getByRole('tab',{name:'Applications',exact:true}).click();await expect(page.locator('#browser-panel')).toBeVisible();await expect(page.locator('#opportunities-panel')).not.toBeVisible();
 await page.getByRole('tab',{name:'My Profile',exact:true}).click();await expect(page.locator('#professional-profile')).toBeVisible();await expect(page.locator('#browser-panel')).not.toBeVisible();await page.goBack();await expect(page.locator('#browser-panel')).toBeVisible();
});

test('email leads button opens a separate view with real role title and research state',async({page,harness})=>{
 harness.replies.set('GET /api/email/leads',{body:{total:1,named:1,unresolved:0,running:0,page:1,pages:1,items:[{id:'alert',title:'Senior Angular Engineer',company:'Example',url:'https://example.com/jobs/123',research_state:'Access or identity blocked',next_action:'Official employer route required',official_candidates:[]}]}});
 await open(page);await page.getByRole('button',{name:'Review received email leads',exact:true}).click();await expect(page.locator('#email-leads-panel')).toBeVisible();await expect(page.locator('#opportunities-panel')).not.toBeVisible();await expect(page.getByRole('heading',{name:'Senior Angular Engineer',exact:true})).toBeVisible();await page.getByRole('button',{name:'Read conversation',exact:true}).click();await expect(page.getByRole('link',{name:'Open Senior Angular Engineer',exact:true})).toHaveAttribute('href','https://example.com/jobs/123');await expect(page.locator('#email-lead-list')).toContainText('Official employer route required');
});

test('batch progress updates automatically and completion emits one two-tone alert',async({page,harness})=>{
 harness.replies.set('GET /api/notifications',{body:{items:[],preferences:{sound:true,desktop:false,quiet_start:22,quiet_end:8},quiet:false}}); // Explicit fixture opt-in; sound is off by default.
 await page.addInitScript(()=>{(window as any).tones=0;(window as any).AudioContext=class{state='running';currentTime=0;destination={};resume(){return Promise.resolve();}createOscillator(){return {frequency:{value:0},connect(){},start(){(window as any).tones++;},stop(){}};}createGain(){return {gain:{value:0},connect(){}};}};});
 harness.replies.set('POST /api/browser/batches',{body:{batch_id:'new-batch',selected:5}});
 const active={id:'new-batch',status:'RUNNING',processed:0,total:5,ready:0,needs_answers:0,agent_checks:0};
 harness.replies.set('GET /api/browser/progress',{body:{batches:[active],documents:[{name:'Cover_letter.pdf',available:true}]}});
 harness.replies.set('GET /api/browser/applications',{body:[{...browserRow,batch_id:'new-batch',state:'PREPARING'}]});
 harness.replies.set('GET /api/browser/progress',{body:{batches:[],documents:[],work_active:false}});
 harness.replies.set('GET /api/browser/applications',{body:[]});
 await page.route('**/api/browser/batches',async route=>{harness.replies.set('GET /api/browser/progress',{body:{active_batch_id:'new-batch',work_active:true,batches:[active],documents:[]}});harness.replies.set('GET /api/browser/applications',{body:[{...browserRow,batch_id:'new-batch',state:'PREPARING'}]});await route.fulfill({json:{batch_id:'new-batch',selected:5}});});
 await open(page,'browser-panel');await page.locator('#browser-batch').click();await expect(page.locator('#browser-progress')).toContainText('0 of 5');await expect(page.locator('#browser-batch')).toBeDisabled();
 harness.replies.set('GET /api/browser/progress',{body:{batches:[{...active,status:'REVIEW',processed:5,ready:5,finished_at:'fixture-complete'}],documents:[{name:'Cover_letter.pdf',available:true}]}});harness.replies.set('GET /api/browser/applications',{body:[{...browserRow,batch_id:'new-batch',state:'READY_FOR_USER_REVIEW'}]});
 await expect(page.locator('#batch-completion')).toContainText('5 ready for review');await expect.poll(()=>page.evaluate(()=>(window as any).tones)).toBe(2);await expect(page.locator('#document-availability')).toContainText('Cover_letter.pdf: approved PDF available');
});

test('unknown answer modal saves explicitly and reuses a versioned profile answer',async({page,harness})=>{
 harness.replies.set('GET /api/browser/applications/fixture-browser/questions',{body:[{key:'question:fixture',label:'Years in B2B SaaS',instructions:'Whole years',options:[],max_length:10}]});
 harness.replies.set('POST /api/browser/applications/fixture-browser/answers',{body:{version:32}});
 await open(page,'browser-panel');await page.getByRole('button',{name:'Answer missing questions',exact:true}).click();await expect(page.locator('#answer-dialog')).toBeVisible();await page.getByLabel('Years in B2B SaaS',{exact:true}).fill('2');await page.getByLabel('Reuse this answer for the same question at other employers').check();await page.getByRole('button',{name:'Save answers and continue',exact:true}).click();await expect(page.locator('#answer-dialog')).not.toBeVisible();await expect(page.locator('#message')).toContainText('profile version 32');expect(harness.writes[0].body.answers[0]).toEqual({key:'question:fixture',value:'2',reuse:true});
});

test('refresh progress requests actual browser synchronization',async({page,harness})=>{
 harness.replies.set('POST /api/browser/sync',{body:{state:'SYNCHRONIZING'}});await open(page,'browser-panel');await page.locator('#browser-refresh').click();await expect.poll(()=>harness.writes.length).toBe(1);expect(harness.writes[0].path).toBe('/api/browser/sync');
});

test('research next alerts provides immediate action feedback',async({page,harness})=>{
 harness.replies.set('GET /api/email/leads',{body:{items:[],total:0,named:0,unresolved:0,running:0,page:1,pages:1}});harness.replies.set('POST /api/email/research',{body:{selected:5,run_id:'fixture'}});await open(page,'email-leads-panel/job-alerts');await page.locator('#research-email-leads').click();await expect(page.locator('#message')).toContainText('research started for 5');expect(harness.writes[0].path).toBe('/api/email/research');
});

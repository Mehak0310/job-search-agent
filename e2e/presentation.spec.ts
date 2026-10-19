import {test,expect,open,job} from './portal-fixture';

const buttonNames=[
 'Notifications (0)','Close notifications','Enable desktop notifications','Build pending batch plans','Save disabled hourly plan',
 'Prepare next review batch (up to 5)','Refresh browser progress','Connect/login to LinkedIn','Connect/login to Naukri','Run discovery','Prepare eligible queue','Export review workbook','Refresh recommendations','Review received email leads','Refresh','Apply filters','Clear filters','Reset to preferences','Previous','Next','Import file','Save and rescore jobs','Save professional profile and rescore','Replace local reference','Parse attached resume locally','Save live search background','Close','Switch to application tab','Reinspect form / confirmation','Fill newly supported answers','I submitted this application','Remove unavailable job','Edit prepared text','Frontend fixture','Shortlist','Review or edit application','Preview Gmail draft','Approve this exact unsent draft','Close draft preview','Prepare browser application','Prepare application text','Accept fact','Reject','Answer missing questions','Close answers','Save answers and continue','Research next 5 alert links','Previous alerts','Next alerts','Job alerts','Draft approvals','Recalculate pending priority','Collapse sidebar','Settings','Refresh view','View role details','Read conversation'];

test('every rendered button belongs to the interaction coverage inventory',async({page,harness},info)=>{
 await open(page,'opportunities-panel');const names=await page.locator('button').allTextContents();const unknown=names.map(s=>s.trim()).filter(s=>!buttonNames.includes(s));expect(unknown).toEqual([]);
 const missing=buttonNames.filter(s=>s!=='Read conversation'&&!names.map(n=>n.trim()).includes(s));expect(missing).toEqual([]);
 await info.attach('button-coverage-inventory',{body:JSON.stringify({buttons:names.map(s=>s.trim()),count:names.length},null,2),contentType:'application/json'});
});

test('all rendered anchors have labels, safe destinations and external tab protection',async({page,harness})=>{
 await open(page,'opportunities-panel');const links=await page.locator('a').evaluateAll(nodes=>nodes.map(a=>({text:a.textContent?.trim(),href:a.getAttribute('href'),target:a.getAttribute('target'),rel:a.getAttribute('rel')})));
 for(const link of links){expect(link.text).toBeTruthy();expect(link.href).toMatch(/^(?:https?:\/\/|#)/);if(link.href?.startsWith('http')){expect(link.target).toBe('_blank');expect(link.rel).toContain('noopener');expect(link.rel).toContain('noreferrer');}}
});

for(const width of [390,768,1365])test('visual layout, controls and dialog at '+width,async({page,harness},info)=>{
 await page.setViewportSize({width,height:900});await open(page,'m3-panel');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 const grid=await page.locator('#application-queue').evaluate(e=>getComputedStyle(e).gridTemplateColumns.split(' ').length);expect(grid).toBe(width<=760?1:2);
 await page.screenshot({path:info.outputPath('workspace.png')});
 await page.locator('.packet-card').getByRole('button',{name:'Edit prepared text'}).click();
 const dialog=page.locator('#detail-dialog');await expect(dialog).toBeVisible();
 await expect(page.locator('#close-dialog')).toBeInViewport();
 const dimensions=await dialog.evaluate(e=>({outer:e.scrollHeight<=e.clientHeight,left:e.getBoundingClientRect().left,right:e.getBoundingClientRect().right}));expect(dimensions.outer).toBe(true);expect(dimensions.left).toBeGreaterThanOrEqual(0);expect(dimensions.right).toBeLessThanOrEqual(width);
 await expect(page.getByLabel('Subject',{exact:true})).toBeVisible();await page.screenshot({path:info.outputPath('packet-editor.png')});
 await page.keyboard.press('Escape');await expect(dialog).not.toBeVisible();
});

test('required preference fields prevent accidental empty save',async({page,harness})=>{
 await open(page,'professional-profile');await page.locator('.command-subnav').getByRole('link',{name:'Preferences',exact:true}).click();await page.locator('#profile-titles').fill('');await page.locator('#profile-form button').click();expect(harness.writes).toHaveLength(0);expect(await page.locator('#profile-titles').evaluate((e:HTMLInputElement)=>e.validity.valueMissing)).toBe(true);
});

test('file forms require an explicit file selection',async({page,harness})=>{
 await open(page,'tools-panel');await page.locator('#import-form button').click();await page.getByRole('tab',{name:'My Profile',exact:true}).click();await page.locator('.command-subnav').getByRole('link',{name:'Documents',exact:true}).click();await page.getByText('Resume reference and explicit local parsing',{exact:true}).click();await page.locator('#resume-form button').click();expect(harness.writes).toHaveLength(0);
});

test('profile mode checkboxes retain the selected preference in save payload',async({page,harness})=>{
 harness.replies.set('PUT /api/profile',{body:{saved:true}});await open(page,'professional-profile');await page.locator('.command-subnav').getByRole('link',{name:'Preferences',exact:true}).click();await page.locator('[name=profile-mode][value=remote]').check();await page.locator('[name=profile-mode][value=onsite]').uncheck();await page.locator('#profile-form button').click();await expect.poll(()=>harness.writes.length).toBe(1);expect(harness.writes[0].body.work_modes).toContain('remote');expect(harness.writes[0].body.work_modes).not.toContain('onsite');
});

test('packet text fields have associated labels and remain keyboard editable',async({page,harness})=>{
 await open(page,'m3-panel');await page.locator('.packet-card').getByRole('button',{name:'Edit prepared text'}).click();
 for(const label of ['Subject','Application email','Portal supporting statement']){const input=page.getByLabel(label,{exact:true});await input.fill('Reviewed fixture content');await expect(input).toHaveValue('Reviewed fixture content');}
 await page.locator('#close-dialog').click();expect(harness.writes).toHaveLength(0);
});

test('all selectable manual tracking states remain available',async({page,harness})=>{
 await open(page,'opportunities-panel');const values=await page.getByRole('combobox',{name:'Manual status for '+job.title}).locator('option').evaluateAll(nodes=>nodes.map(n=>(n as HTMLOptionElement).value));expect(values).toEqual(expect.arrayContaining(['NEW','SHORTLISTED','PREPARING','READY_FOR_REVIEW','APPROVED','SUBMITTED','INTERVIEW','REJECTED','OFFER','NOT_RELEVANT']));
});


test('submission history disables further preparation without disabling evidence inspection',async({page,harness})=>{
 harness.replies.set('GET /api/browser/applications',{body:[{id:'done',company:'Example',title:'Frontend',state:'USER_REPORTED_SUBMITTED',url:'https://example.com/job',inspection:{},missing:[],checks:[],documents:[]}]});await open(page,'browser-panel/applied');
 await page.locator('#browser-applications .review-tools summary').click();await expect(page.getByRole('button',{name:'Fill newly supported answers',exact:true})).toBeDisabled();await expect(page.getByRole('button',{name:'Reinspect form / confirmation',exact:true})).toBeEnabled();
});

test('lost session disables fill and requires the reconstruction flow',async({page,harness})=>{
 harness.replies.set('GET /api/browser/applications',{body:[{id:'lost',job_id:job.id,company:'Example',title:'Frontend',state:'SESSION_LOST',url:'https://example.com/job',inspection:{},missing:[],checks:[],documents:[]}]});await open(page,'browser-panel');
 await page.locator('#browser-applications .review-tools summary').click();await expect(page.getByRole('button',{name:'Fill newly supported answers',exact:true})).toBeDisabled();await expect(page.getByRole('button',{name:'Reconstruct after progress review'})).toBeEnabled();
});

test('failed import re-enables its button and preserves selected file',async({page,harness})=>{
 harness.replies.set('POST /api/import',{status:422,body:{detail:'Invalid fixture JSON'}});await open(page,'tools-panel');await page.locator('#import-file').setInputFiles({name:'fixture.json',mimeType:'application/json',buffer:Buffer.from('invalid')});await page.locator('#import-form button').click();await expect(page.locator('#message')).toContainText('Invalid fixture JSON');await expect(page.locator('#import-form button')).toBeEnabled();expect(await page.locator('#import-file').evaluate((e:HTMLInputElement)=>e.files?.[0]?.name)).toBe('fixture.json');
});

test('failed resume replacement does not claim success',async({page,harness})=>{
 harness.replies.set('POST /api/candidate-profile/resume',{status:422,body:{detail:'Resume format could not be verified'}});await open(page,'professional-profile/documents');await page.getByText('Resume reference and explicit local parsing',{exact:true}).click();await page.locator('#resume-file').setInputFiles({name:'fixture.pdf',mimeType:'application/pdf',buffer:Buffer.from('invalid')});await page.locator('#resume-form button').click();await expect(page.locator('#message')).toContainText('Resume format could not be verified');await expect(page.locator('#message')).not.toContainText('stored');
});

test('dialog closes into its original trigger and has a visible focus outline',async({page,harness})=>{
 await open(page,'m3-panel');const button=page.locator('.packet-card').getByRole('button',{name:'Edit prepared text'});await button.click();await expect(page.locator('#detail-dialog')).toBeVisible();await page.keyboard.press('Escape');await expect(button).toBeFocused();await button.focus();expect(await button.evaluate(e=>getComputedStyle(e).outlineStyle)).not.toBe('none');
});

import {test,expect,open} from './portal-fixture';
test('priority queue shows evidence, position and processing state and refreshes explicitly',async({page,harness})=>{
 harness.replies.set('GET /api/priority-queue',{body:{pending:1,verification:1,items:[{job_id:'ranked',title:'Verified priority role',queue_position:1,state:'PENDING',fit:92,eligibility:'PASS',source:'greenhouse',reason:'Verified fit descending; stable job ID tie-break.',last_processed:'2026-10-19T00:00:00Z'}]}});
 harness.replies.set('POST /api/priority-queue/refresh',{body:{pending:1}});
 await open(page,'browser-panel');await page.locator('.command-subnav').getByRole('link',{name:'Priority Queue',exact:true}).click();
 await expect(page.locator('#priority-list')).toContainText('#1 | Verified priority role');
 await expect(page.locator('#priority-list')).toContainText('92/100PASSgreenhouse');
 await expect(page.locator('#priority-list')).toContainText('2026-10-19');
 await page.getByRole('button',{name:'Recalculate pending priority'}).click();
 await expect.poll(()=>harness.writes.length).toBe(1);expect(harness.writes[0].path).toBe('/api/priority-queue/refresh');
});
test('priority API failure never blanks application history or browser progress',async({page,harness})=>{
 harness.replies.set('GET /api/priority-queue',{status:503,body:{detail:'Isolated priority failure'}});
 await open(page,'browser-panel');await expect(page.locator('#browser-applications>.job')).toHaveCount(1);
 await expect(page.locator('#priority-status')).toContainText('Isolated priority failure');await expect(page.locator('#browser-progress')).not.toBeEmpty();
});

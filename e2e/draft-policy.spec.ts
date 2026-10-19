import {test,expect,open} from './portal-fixture';

test('Opportunities defaults to highest fit and minimum fit remains a threshold',async({page})=>{
 const requests:string[]=[];page.on('request',r=>{if(new URL(r.url()).pathname==='/api/jobs')requests.push(r.url());});
 await open(page);await expect(page.locator('#sort-filter')).toHaveValue('score_desc');
 expect(new URL(requests[0]).searchParams.get('sort')).toBe('score_desc');
 await page.locator('#score-filter').selectOption('70');
 const request=page.waitForRequest(r=>new URL(r.url()).pathname==='/api/jobs'&&new URL(r.url()).searchParams.get('min_score')==='70');
 await page.getByRole('button',{name:'Apply filters',exact:true}).click();expect(new URL((await request).url()).searchParams.get('sort')).toBe('score_desc');
 await page.locator('#reset-preferences').click();await expect(page.locator('#sort-filter')).toHaveValue('score_desc');
});

test('old freshness sort migrates without erasing other saved filters',async({page})=>{
 await page.addInitScript(()=>{if(!sessionStorage.getItem('jobFilters'))sessionStorage.setItem('jobFilters',JSON.stringify({'sort-filter':'priority',search:'Angular'}));});
 await open(page);await expect(page.locator('#sort-filter')).toHaveValue('score_desc');await expect(page.locator('#search')).toHaveValue('Angular');await page.reload();await expect(page.locator('#sort-filter')).toHaveValue('score_desc');
});

test('leaving email leads clears the stale email-only notification',async({page})=>{
 await open(page);await page.locator('#email-leads').click();await expect(page.locator('#message')).toContainText('Showing received email leads');
 await page.getByRole('tab',{name:'Find Jobs',exact:true}).click();await expect(page.locator('#message')).not.toContainText('Showing received email leads');
});

test('application status requires exact preview approval and disables live creation',async({page})=>{
 await open(page,'m3-panel');await expect(page.locator('#m3-status')).toContainText('approval of the exact preview');await expect(page.locator('#m3-status')).toContainText('Live creation is disabled');
});

test('preview failure gives an actionable error',async({page,harness})=>{
 harness.replies.set('POST /api/m3/packets/fixture-packet/draft-preview',{status:422,body:{detail:'Approved document unavailable'}});
 await open(page);await page.getByRole('button',{name:'Preview Gmail draft',exact:true}).click();await expect(page.locator('#message')).toContainText('Approved document unavailable');
});

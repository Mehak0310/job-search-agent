import { test as base, expect } from '@playwright/test';

type Reply = { status?: number; body: unknown; delay?: number };
type Harness = { writes: {path:string; method:string; body:any}[]; replies: Map<string, Reply> };
export const test = base.extend<{ harness: Harness }>({
  harness: async ({ page, context, baseURL }, use) => {
    const scriptErrors:string[]=[];page.on('pageerror',error=>scriptErrors.push(error.message));
    const harness:Harness={writes:[],replies:new Map()};
    harness.replies.set('GET /api/notifications',{body:{items:[],preferences:{sound:false,desktop:false,quiet_start:22,quiet_end:8},quiet:false}});
    harness.replies.set('GET /api/inbox/messages',{body:{items:[],scope:'fixture'}});harness.replies.set('GET /api/activity/runs',{body:{items:[]}});
    await page.route('**/api/**',async route=>{
      const req=route.request(),path=new URL(req.url()).pathname,key=req.method()+' '+path;
      const reply=harness.replies.get(key);
      if(req.method()!=='GET'){
        let body:any;try{body=req.postDataJSON();}catch{body=req.postData();}
        harness.writes.push({path,method:req.method(),body});
        // No UI test can mutate the real database or invoke an external action.
        if(!reply)return route.fulfill({status:409,json:{detail:'Test blocked unconfigured write'}});
      }
      if(reply){if(reply.delay)await new Promise(r=>setTimeout(r,reply.delay));return route.fulfill({status:reply.status||200,json:reply.body});}
      return route.continue(); // Read-only local GETs exercise the actual server.
    });
    await context.route(url=>['http:','https:'].includes(url.protocol)&&url.origin!==new URL(baseURL||'http://127.0.0.1:8000').origin,route=>route.fulfill({contentType:'text/html',body:'External navigation intercepted by Playwright; no network request made.'}));
    await use(harness);
    expect(scriptErrors,'No uncaught application JavaScript errors').toEqual([]);
  },
});
export { expect };
export async function open(page:any,section='opportunities-panel'){
  await page.goto(section==='opportunities-panel'?'/':'/#'+section);
  await expect(page.locator('#page-status')).not.toHaveText('Page 1');
  await expect(page.locator('#browser-progress')).not.toBeEmpty();
  if(section==='opportunities-panel')await page.locator('.filter-disclosure').evaluate((e:HTMLDetailsElement)=>e.open=true);
}

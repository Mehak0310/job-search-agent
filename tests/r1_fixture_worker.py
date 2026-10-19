"""Synthetic subprocess driver. Never used by normal runtime or real browser sessions."""
import argparse,json,socket,time
from contextlib import contextmanager
from pathlib import Path
from playwright.sync_api import sync_playwright
from job_agent.database import Database
from job_agent import browser_applications as runner,browser_workers
from job_agent.browser_forms import NetworkBoundary


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--db',required=True);parser.add_argument('--batch',required=True);parser.add_argument('--workflow',required=True);parser.add_argument('--hold',action='store_true');args=parser.parse_args()
    db=Database(args.db)
    original_workers=browser_workers.BrowserWorkers
    class FixtureWorkers(original_workers):
        def __init__(self,db,lease_seconds=3):super().__init__(db,lease_seconds)
    browser_workers.BrowserWorkers=FixtureWorkers
    runner.ensure_browser=lambda db:{'webSocketDebuggerUrl':'ws://127.0.0.1/fixture-session'}
    runner.public_url=lambda url:url
    def dns(*args,**kwargs):return [(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',443))]
    runner.NetworkBoundary=lambda host:NetworkBoundary(host,dns=dns)
    with db.transaction() as conn:profile=json.loads(conn.execute('SELECT config FROM candidate_profiles_v2').fetchone()[0])
    manifest=json.loads((db.path.parent/'documents/manifest.json').read_text())
    runner.approved_facts=lambda db:(profile,{'full_name':'Synthetic Candidate','email':'fixture@example.com','country':'India'}, {},manifest)
    def html(index):
        extra='<label>Years in B2B SaaS<input id="saas" required></label><label>I confirm the information provided is accurate<input id="declare" required></label>' if index==1 else ''
        upload='<label>Resume<input id="resume" type="file" required></label><span id="filename"></span>' if index==0 else ''
        return '<h1>R1 Frontend '+str(index)+'</h1><p>Requirements: React and TypeScript. Build accessible frontend components and test interfaces. '+('Documented fixture responsibilities. '*12)+'</p><form><label>Full name<input id="name" required></label><label>Email<input id="email" type="email" required></label>'+extra+upload+'<button type="submit">Submit application</button></form><script>window.submits=0;document.querySelector("form").onsubmit=e=>{window.submits++;e.preventDefault()};if(window.resume)resume.onchange=async()=>{await fetch("https://grnhse-prod-jben-us-west-2.s3.us-west-2.amazonaws.com/",{method:"POST",body:new FormData()});filename.textContent=resume.files[0].name;};</script>'
    @contextmanager
    def connection():
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True);context=browser.new_context()
            def respond(route):
                request=route.request
                if request.url.startswith('https://grnhse-prod-jben-us-west-2.s3.us-west-2.amazonaws.com/'):
                    return route.fulfill(status=204,headers={'access-control-allow-origin':'*'})
                if request.url.startswith('https://job-boards.greenhouse.io/r1-fixture/jobs/') and request.method=='GET':
                    index=int(request.url.rsplit('/',1)[1])%10
                    return route.fulfill(status=403 if index==3 else 200,content_type='text/html',body=html(index))
                return route.abort()
            context.route('**/*',respond)
            try:yield browser
            finally:browser.close()  # Only this headless synthetic browser; never port9224.
    def prepare(store,item,browser,metadata,allow_upload):
        if args.hold:
            store.update(item['id'],inspection={'stage':'Fixture worker held for termination test','answered':1})
            while True:time.sleep(.2)
        index=int(item['url'].rsplit('/',1)[1])%10
        if index==4:
            with db.transaction() as conn:conn.execute("UPDATE job_operational_state SET headcount_state='UNKNOWN' WHERE job_id=?",(item['job_id'],))
        if index==2:store.update(item['id'],target_id='nonexistent-fixture-target')
        runner.prepare_one(store,store.get(item['id']),browser,metadata,allow_upload)
        with store.db.transaction() as conn:
            if any(page.evaluate('window.submits||0') for context in browser.contexts for page in context.pages):raise RuntimeError('Fixture detected a submission')
        time.sleep(.5)
    runner.execute_batch(db,args.batch,True,workflow_id=args.workflow,_connection=connection,_prepare=prepare)


if __name__=='__main__':main()

"""Strict GET-only acceptance of the running command center; own QA browser only."""
import hashlib
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from playwright.sync_api import sync_playwright, expect


def main():
    expect.set_options(timeout=15000)
    parser=argparse.ArgumentParser()
    parser.add_argument('--output-dir',default='data/command-center-activation')
    parser.add_argument('--orchestration',action='store_true')
    options=parser.parse_args()
    target = Path(options.output_dir)
    target.mkdir(parents=True,exist_ok=True)
    checks, errors, blocked = {}, [], []
    source = Path('job_agent')
    digest = hashlib.sha256()
    for path in sorted(source.rglob('*')):
        if path.is_file() and path.suffix in {'.py','.js','.html','.css'}:
            digest.update(path.relative_to(source).as_posix().encode()+b'\0'+path.read_bytes()+b'\0')
    with httpx.Client(base_url='http://127.0.0.1:8000',trust_env=False,timeout=30) as api:
        health = api.get('/api/health').json()
        progress = api.get('/api/browser/progress').json()
        active = api.get('/api/browser/applications').json()
        history = api.get('/api/browser/applications?include_history=true').json()
        queue = api.get('/api/priority-queue').json()
        sources = api.get('/api/sources').json()
        inbox = api.get('/api/inbox/messages').json()
        jobs = api.get('/api/jobs?page=1&page_size=50&min_score=0&sort=score_desc').json()['items']
        unknown = next(j for j in jobs if j['card']['requirement_assessment']['state']=='UNKNOWN' and j['card']['requirement_assessment']['reasons'])
        # Backend code is loaded at startup; static assets are served from disk.
        # Capture a backend manifest only when the entire startup tree matches.
        manifest_path=target/'backend-manifest.json'
        python_files={str(path.relative_to(source)):hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(source.rglob('*.py'))}
        if not manifest_path.exists():
            assert health['runtime']['source_sha256']==digest.hexdigest()
            manifest_path.write_text(json.dumps({'startup_source_sha256':digest.hexdigest(),'python_files':python_files},indent=2))
        manifest=json.loads(manifest_path.read_text())
        checks['running_repaired_source'] = health['runtime']['source_sha256']==manifest['startup_source_sha256'] and python_files==manifest['python_files']
        assets={}
        for path in sorted((source/'static').glob('*')):
            if path.suffix in {'.js','.css','.html'}:
                response=api.get('/static/'+path.name)
                assets[path.name]=hashlib.sha256(response.content).hexdigest()
                assert response.status_code==200 and response.content==path.read_bytes()
        checks['current_static_assets_served']=bool(assets)
        (target/'served-assets.json').write_text(json.dumps(assets,indent=2))
        checks['safety_flags'] = health['submission_enabled'] is False and health['runtime']['live_draft_creation'] is False
        checks['canonical_history_separated'] = all(r['application_outcome'] not in {'USER_REPORTED_SUBMITTED','SUBMISSION_CONFIRMED'} for r in active)
        checks['lost_session_retains_submission'] = any(r['session_health']=='LOST' and r['application_outcome']=='USER_REPORTED_SUBMITTED' for r in history)
        checks['strict_queue'] = all(r['eligibility']=='PASS' for r in queue['items'] if r['state']=='PENDING')
        checks['source_projection'] = bool(sources) and all('retained_job_count' in r and 'last_run_metrics' in r for r in sources)
        checks['retained_inbox_projection'] = isinstance(inbox['items'],list)
        if options.orchestration:
            notes=api.get('/api/notifications');plans=api.get('/api/orchestration/plans');schedules=api.get('/api/orchestration/schedules')
            checks['orchestration_projections_active']=all(response.status_code==200 for response in [notes,plans,schedules])
            checks['schedules_remain_disabled']=not schedules.json()['activation_enabled'] and all(not r['enabled'] for r in schedules.json()['items'])
            checks['two_actor_policy']=plans.json()['max_browser_workers']==2 and plans.json()['max_active_batches']==1
    def guard(route):
        req=route.request
        if req.method!='GET' or urlsplit(req.url).netloc!='127.0.0.1:8000':
            blocked.append({'method':req.method,'external':urlsplit(req.url).netloc!='127.0.0.1:8000'})
            route.abort()
        else:route.continue_()
    routes = [('home','home-panel/overview'),('jobs','opportunities-panel/all-jobs'),('applications','browser-panel/priority-queue'),('inbox','email-leads-panel/job-alerts'),('sources','discovery-panel/source-health'),('profile','professional-profile/career-facts')]
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        context=browser.new_context(viewport={'width':1440,'height':1000})
        context.route('**/*',guard)
        page=context.new_page()
        page.on('pageerror',lambda error:errors.append(str(error)))
        if options.orchestration:
            page.goto('http://127.0.0.1:8000/')
            page.locator('#notification-center-button').click()
            expect(page.locator('#notification-center')).to_be_visible()
            page.get_by_role('button',name='Close notifications',exact=True).click()
            checks['notification_center_read_only']=True
        for name,route in routes:
            page.goto('http://127.0.0.1:8000/#'+route)
            expect(page.locator('.command-subnav [aria-current=page]')).to_be_visible()
            expect(page.locator('#browser-progress')).not_to_be_empty()
            expect(page.locator('#command-worker')).not_to_have_text('Checking worker')
            checks[name+'_loads'] = page.get_by_role('tab').count()==6
            if name=='jobs':
                page.locator('.filter-disclosure').evaluate('(e)=>e.open=true')
                page.locator('#clear-filters').click()
                page.locator('#jobs>article.job').first.wait_for()
                expect(page.locator('#command-job-detail')).not_to_be_empty()
                checks['apply_link_outside_drawer']=page.locator('#jobs .vacancy-link').count()>0
                page.locator('.filter-disclosure').evaluate('(e)=>e.open=false')
                for card in page.locator('#jobs>article.job').all():
                    if card.get_attribute('data-job-id')==unknown['id']:
                        card.get_by_role('button',name='View role details',exact=True).click()
                        break
                reason=unknown['card']['requirement_assessment']['reasons'][0]
                expect(page.locator('#command-job-detail')).to_contain_text(reason)
                checks['exact_unknown_reason_visible']=reason in page.locator('#command-job-detail').inner_text()
            if name=='sources':expect(page.locator('#command-source-table tbody tr')).to_have_count(len(sources))
            page.screenshot(path=str(target/(name+'-desktop.png')))
            page.set_viewport_size({'width':390,'height':844})
            checks[name+'_mobile_no_overflow']=page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.screenshot(path=str(target/(name+'-mobile.png')))
            page.set_viewport_size({'width':1440,'height':1000})
        page.goto('http://127.0.0.1:8000/#browser-panel/applied')
        reported=next(r for r in history if r['application_outcome']=='USER_REPORTED_SUBMITTED')
        card=page.locator('article[data-application-id="'+reported['id']+'"]')
        expect(card).to_contain_text(reported['status_message'])
        checks['ui_submission_distinct_from_browser_loss']='Browser: lost' in card.inner_text()
        page.goto('http://127.0.0.1:8000/#browser-panel/preparing')
        expect(page.locator('#browser-progress')).not_to_be_empty()
        old=page.locator('#browser-progress').inner_text()
        page.reload()
        expect(page.locator('#browser-progress')).to_have_text(old)
        other=context.new_page()
        other.goto('http://127.0.0.1:8000/#browser-panel/preparing')
        expect(other.locator('#browser-progress')).to_have_text(old)
        checks['reload_and_new_tab_recover']=True
        page.route('**/api/sources',lambda route:route.fulfill(status=503,json={'detail':'Isolated source failure'}))
        page.reload()
        expect(page.locator('#browser-progress')).not_to_be_empty()
        expect(page.locator('#discovery-panel .section-error')).to_contain_text('Isolated source failure')
        checks['source_failure_isolated_and_retained']=page.locator('#browser-applications article.job').count()==len(active)
        browser.close()
    checks['no_script_errors']=not errors
    checks['no_write_or_external_attempt']=not blocked
    result={'checks':checks,'errors':errors,'blocked':blocked,'runtime':health['runtime'],'counts':{'active':len(active),'history':len(history),'eligible':queue['pending'],'verification':queue['verification'],'inbox':len(inbox['items'])},'read_only':True}
    (target/'acceptance.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'checks':checks,'errors':errors,'blocked':blocked},indent=2))
    assert all(checks.values())


if __name__=='__main__':main()

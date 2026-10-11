"""Milestone 2A.2/2A.3 real Chrome QA."""
import json,time
from pathlib import Path
from playwright.sync_api import sync_playwright
BASE="http://127.0.0.1:8011"; OUT=Path("artifacts/browser-qa-2a23");OUT.mkdir(parents=True,exist_ok=True)
results=[];console_errors=[];failed=[]
def check(name,value,detail=""): results.append({"scenario":name,"passed":bool(value),"detail":detail})
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",headless=True);page=browser.new_page(viewport={"width":1440,"height":1000})
 page.on("console",lambda m:console_errors.append(m.text) if m.type=="error" else None);page.on("requestfailed",lambda r:failed.append({"url":r.url,"error":r.failure}))
 page.goto(BASE,wait_until="networkidle");check("Dashboard loads",page.title()=="Job Search Workspace")
 page.click('#clear-filters');page.wait_for_timeout(600);total=int(page.locator('#result-count').inner_text().split()[0]);check("Total counts accurate",total==page.request.get(BASE+'/api/jobs?page=1&page_size=50').json()['total'],str(total))
 check("Pagination works",not page.locator('#next-page').is_disabled());page.click('#next-page');page.wait_for_timeout(500);check("Pagination advances",'Page 2' in page.locator('#page-status').inner_text())
 page.select_option('#freshness-filter','48h');page.click('#filters button[type=submit]');page.wait_for_timeout(500);check("Freshness filters work",int(page.locator('#result-count').inner_text().split()[0])>0)
 page.select_option('#sort-filter','newest');page.click('#filters button[type=submit]');page.wait_for_timeout(400);check("Newest-first sorting works",page.locator('.job').count()>0)
 page.select_option('#freshness-filter','');page.select_option('#eligibility-filter','ELIGIBLE');page.click('#filters button[type=submit]');page.wait_for_timeout(400);check("India eligibility filter works",page.locator('.job').count()>0)
 page.select_option('#location_bucket-filter','DELHI_NCR,GURUGRAM,NOIDA,GREATER_NOIDA,MOHALI,CHANDIGARH,REMOTE_INDIA');page.click('#filters button[type=submit]');page.wait_for_timeout(400);check("Preferred-location filter works",page.locator('.job').count()>0)
 page.select_option('#location_bucket-filter','GURUGRAM');page.click('#filters button[type=submit]');page.wait_for_timeout(400);check("Gurgaon/Gurugram normalization works",page.locator('.job').count()>0)
 page.click('#clear-filters');page.select_option('#experience-filter','5-8');page.click('#filters button[type=submit]');page.wait_for_timeout(400);check("Experience filtering works",page.locator('.job').count()>0)
 page.select_option('#experience-filter','');page.fill('#skills-filter','React');page.click('#filters button[type=submit]');page.wait_for_timeout(400);check("Skills filtering works",page.locator('.job').count()>0)
 page.select_option('#eligibility-filter','ELIGIBLE');page.select_option('#category-filter','FRONTEND');page.click('#filters button[type=submit]');page.wait_for_timeout(400);check("Multiple filters compose",page.locator('.job').count()>0)
 page.click('#clear-filters');page.wait_for_timeout(400);check("Clear Filters works",page.locator('.job').count()==50)
 page.select_option('#eligibility-filter','ELIGIBLE');page.click('#filters button[type=submit]');page.reload(wait_until='networkidle');check("Filters persist",page.locator('#eligibility-filter').input_value()=='ELIGIBLE')
 page.click('#clear-filters');page.wait_for_timeout(400);page.locator('.job h3 button').first.click();page.wait_for_selector('#detail-dialog[open]');body=page.locator('#detail-body').inner_text();check("Details show publication evidence",'Published:' in body and 'First discovered:' in body);link=page.locator('#detail-body a.source-link').first;check("Source platform links work",link.count()==1 and link.get_attribute('href').startswith('https://'));page.screenshot(path=OUT/'detail.png');page.click('#close-dialog')
 button=page.locator('.job .job-actions button:not([disabled])').first;if_count=button.count();
 if if_count: button.click();page.wait_for_timeout(500)
 page.reload(wait_until='networkidle');check("Manual shortlist persists",page.locator('.job .job-actions button',has_text='Shortlisted').count()>0)
 page.click('#run-discovery');page.wait_for_timeout(250);started=page.locator('#discovery-status').inner_text().startswith(('RUNNING','COMPLETED','PARTIAL'));check("Discovery progress displays",started)
 for _ in range(30):
  if not page.locator('#run-discovery').is_disabled():break
  time.sleep(.5)
 page.set_viewport_size({"width":768,"height":900});page.screenshot(path=OUT/'dashboard-mobile.png');check("No console errors or failed local requests",not console_errors and not [x for x in failed if x['url'].startswith(BASE)],json.dumps({"console":console_errors,"failed":failed}))
 browser.close()
report={"results":results,"passed":sum(x['passed'] for x in results),"total":len(results),"console_errors":console_errors,"failed_requests":failed};(OUT/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))

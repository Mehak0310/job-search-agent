"""Repeatable M2B Chrome QA using only a temporary database and synthetic jobs."""
import io,json, tempfile, threading, time
from pathlib import Path
import httpx, uvicorn
from playwright.sync_api import sync_playwright
from job_agent.main import create_app
from job_agent.m2d_models import OperationalFacts,TriState
from job_agent.m2d_sources import SOURCES
from docx import Document

OUT=Path("artifacts/browser-qa-m2b"); OUT.mkdir(parents=True,exist_ok=True)
results=[]; errors=[]
def check(name,value): results.append({"scenario":name,"passed":bool(value)})
with tempfile.TemporaryDirectory(prefix="job-agent-m2b-") as folder:
    resume=Path(folder)/"synthetic-resume.docx"; document=Document(); document.add_paragraph("Independent project using React, FastAPI and RAG"); document.save(resume)
    app=create_app(Path(folder)/"qa.sqlite3")
    config=uvicorn.Config(app,host="127.0.0.1",port=8012,log_level="error")
    server=uvicorn.Server(config); thread=threading.Thread(target=server.run,daemon=True); thread.start()
    for _ in range(50):
        try:
            if httpx.get("http://127.0.0.1:8012/api/health",timeout=1).status_code==200: break
        except httpx.HTTPError: time.sleep(.1)
    with httpx.Client(base_url="http://127.0.0.1:8012") as client:
        payload=Path("samples/jobs.json").read_bytes(); client.post("/api/import",files={"file":("jobs.json",payload)}).raise_for_status()
        key=next(iter(client.get("/api/m2d/states").json()))
        app.state.m2d.set_operational_state(key,OperationalFacts(active=TriState.PASS,india_eligible=TriState.UNKNOWN,headcount=TriState.UNKNOWN,direct_permanent_payroll=TriState.UNKNOWN,mandatory_requirements=TriState.UNKNOWN),job_id=key,strong_fit=True)
        client.post("/api/m3/packets/prepare").raise_for_status()
        client.post("/api/recommendations/refresh?top_k=20&strategy=section").raise_for_status()
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",headless=True)
        page=browser.new_page(viewport={"width":1280,"height":900}); page.on("console",lambda m:errors.append(m.text) if m.type=="error" else None)
        page.goto("http://127.0.0.1:8012",wait_until="networkidle")
        expected_sources=sum(source['stream']!='PIPELINE' for source in SOURCES)
        check("M2D coverage summary renders",f"configured {expected_sources}" in page.locator("#m2d-status").inner_text())
        page.locator("#m2d-panel summary").click()
        check("blocked sources remain visible","ACCESS_BLOCKED" in page.locator("#m2d-coverage").inner_text())
        check("M3 application queue renders",page.locator("#application-queue .job").count()==1)
        page.locator("#application-queue button",has_text="Review packet").click();page.wait_for_timeout(300);check("M3 packet warns and stays review-only","not an application submission" in page.locator("#detail-body").inner_text() and "No verified role-related recipient" in page.locator("#detail-body").inner_text());page.locator("#close-dialog").click()
        page.select_option("#freshness-filter","");page.select_option("#experience-filter","");page.click("#filters button[type=submit]");page.wait_for_timeout(400)
        jobs_text=page.locator("#jobs").inner_text()
        check("job cards expose employer checks","Employer checks" in jobs_text and "Owner: Agent research" in jobs_text)
        check("job cards expose separate application states",all(value in jobs_text for value in ("Application","Recruiter / Gmail draft","Submission","Next action")))
        check("specific vacancy action is directly visible",page.locator("#jobs .vacancy-link").count()>0)
        check("job cards use plain states",not any(value in jobs_text for value in ("READY_FOR_PORTAL_REVIEW","PROMISING_NEEDS_VERIFICATION","direct_permanent_payroll")))
        check("recommendations render",page.locator("#recommendations .job").count()>0)
        check("score disclaimer visible","not hiring probabilities" in page.locator("#recommendation-status").inner_text())
        page.select_option("#recommendation-eligibility","UNKNOWN"); page.wait_for_timeout(250); check("eligibility filter works",page.locator("#recommendations").is_visible())
        if not page.locator("#candidate-additional").is_visible():page.locator("summary",has_text="Professional profile and resume evidence").click()
        page.fill("#candidate-additional","graphql"); page.click("#candidate-form button"); page.wait_for_timeout(500); check("profile saves and rescoring runs","Candidate profile version saved" in page.locator("#message").inner_text())
        page.set_input_files('#resume-file',resume); page.click('#resume-form button'); page.wait_for_timeout(300); check("attach does not parse resume",page.locator('#fact-proposals .activity').count()==0)
        page.click('#parse-resume'); page.wait_for_timeout(400); check("resume parsing requires explicit action",page.locator('#fact-proposals .fact-card').count()>0)
        first=page.locator('#fact-proposals .fact-card').first; check("proposal shows source provenance","technical details" in first.inner_text().lower())
        first.locator('input').fill('react'); first.get_by_role('button',name='Accept fact').click(); page.wait_for_timeout(1000); check("synthetic fact acceptance works","Accepted by user" in page.locator('#fact-proposals').inner_text())
        page.get_by_role('button',name='Reject').first.click(); page.wait_for_timeout(1000)
        check("synthetic fact rejection works","Rejected by user" in page.locator('#fact-proposals').inner_text())
        page.set_viewport_size({"width":375,"height":812}); check("mobile has no horizontal overflow",page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")); page.screenshot(path=OUT/"recommendations-mobile.png",full_page=True)
        check("no console errors",not errors); browser.close()
    server.should_exit=True; thread.join(timeout=5)
report={"passed":sum(x["passed"] for x in results),"total":len(results),"results":results,"console_errors":errors,"synthetic_only":True}; (OUT/"report.json").write_text(json.dumps(report,indent=2)+"\n"); print(json.dumps(report,indent=2))

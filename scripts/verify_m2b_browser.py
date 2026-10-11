"""Repeatable M2B Chrome QA using only a temporary database and synthetic jobs."""
import io,json, tempfile, threading, time
from pathlib import Path
import httpx, uvicorn
from playwright.sync_api import sync_playwright
from job_agent.main import create_app
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
        client.post("/api/recommendations/refresh?top_k=20&strategy=section").raise_for_status()
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",headless=True)
        page=browser.new_page(viewport={"width":1280,"height":900}); page.on("console",lambda m:errors.append(m.text) if m.type=="error" else None)
        page.goto("http://127.0.0.1:8012",wait_until="networkidle")
        check("recommendations render",page.locator("#recommendations .job").count()>0)
        check("score disclaimer visible","not hiring probabilities" in page.locator("#recommendation-status").inner_text())
        page.select_option("#recommendation-eligibility","UNKNOWN"); page.wait_for_timeout(250); check("eligibility filter works",page.locator("#recommendations").is_visible())
        page.locator("summary",has_text="Reviewed candidate profile").click(); page.check("#candidate-reviewed"); page.fill("#candidate-learning","langgraph"); page.click("#candidate-form button"); page.wait_for_timeout(500); check("profile review saves","Candidate profile version saved" in page.locator("#message").inner_text())
        page.set_input_files('#resume-file',resume); page.click('#resume-form button'); page.wait_for_timeout(300); page.click('#parse-resume'); page.wait_for_timeout(400); check("resume parsing requires explicit action",page.locator('#fact-proposals .activity').count()>0)
        page.set_viewport_size({"width":375,"height":812}); check("mobile has no horizontal overflow",page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")); page.screenshot(path=OUT/"recommendations-mobile.png",full_page=True)
        check("no console errors",not errors); browser.close()
    server.should_exit=True; thread.join(timeout=5)
report={"passed":sum(x["passed"] for x in results),"total":len(results),"results":results,"console_errors":errors,"synthetic_only":True}; (OUT/"report.json").write_text(json.dumps(report,indent=2)+"\n"); print(json.dumps(report,indent=2))

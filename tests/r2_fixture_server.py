"""Disposable R2 server. Its only Gmail adapter is an in-memory fake."""
import json,tempfile,threading
from pathlib import Path
import uvicorn
from tests.test_r2 import ready
from tests.test_automatic_drafts import Adapter
from job_agent.main import create_app
from job_agent.database import now


def main():
    with tempfile.TemporaryDirectory(prefix='job-agent-r2-') as temporary:
        db,engine,packet=ready(Path(temporary))
        with db.transaction() as c:
            detail=json.loads(c.execute('SELECT discovery_detail FROM jobs').fetchone()[0]);detail['evidence']={'origin':'received_alert','metadata_only':False,'official_jd_url':'https://example.com/jobs/role-1','source_message_refs':['r2-message']}
            detail['requirements_source']['source_url']='https://job-boards.greenhouse.io/r2-fixture/jobs/123'
            c.execute('UPDATE jobs SET discovery_detail=?',(json.dumps(detail),))
            c.execute('INSERT INTO email_message_metadata VALUES(?,?,?,?)',('r2-message','R2 Recruiter <ria@example.com>','R2 Frontend opportunity','2026-10-19T00:00:00Z'))
            c.execute("INSERT INTO m2d_tasks(task_id,kind,job_key,stream,category,payload,status,priority,due_at,attempts,max_attempts,checkpoint,created_at,updated_at) VALUES('r2-task','VERIFICATION',?,'GMAIL','EMAIL_OFFICIAL_JD','{}','COMPLETED',1,?,1,3,'{}',?,?)",(packet['job_id'],now(),now(),now()))
            c.execute("UPDATE jobs SET application_url='https://job-boards.greenhouse.io/r2-fixture/jobs/123',canonical_application_url='https://job-boards.greenhouse.io/r2-fixture/jobs/123'")
        from job_agent.browser_store import BrowserStore
        from job_agent.service import JobService
        from job_agent.reconciliation_r2 import reconcile
        store=BrowserStore(db);batch=store.batch([packet['job_id']],1);application=batch['applications'][0]
        store.update(application['id'],state='NEEDS_USER_ANSWER',missing=['Country','Years in unusual domain'])
        folder=db.path.parent/'browser-applications';folder.mkdir(exist_ok=True)
        (folder/(application['id']+'.json')).write_text(json.dumps({'inventory':[{'id':'country','label':'Country','type':'text','required':True,'visible':True,'value':''},{'id':'domain','label':'Years in unusual domain','type':'text','required':True,'visible':True,'value':''},{'id':'consent','label':'I certify the answers are accurate','type':'checkbox','required':True,'visible':True,'value':False}]}))
        JobService(db).record_confirmed_application_answers({'country':'India'},'explicit isolated fixture confirmation');reconcile(db)
        with db.transaction() as c:c.execute("UPDATE browser_batches SET status='COMPLETED'")
        from job_agent import browser_applications
        browser_applications.launch_sync_worker=lambda *args,**kwargs:1  # No employer browser in this fixture.
        app=create_app(db.path);fake=Adapter(db);fake.isolated_test_adapter=True;app.state.r2_draft_adapter=fake
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=8018,log_level='warning'))
        @app.get('/__r2/evidence')
        def evidence():
            with db.transaction() as c:operations=[dict(r) for r in c.execute('SELECT state,gmail_draft_id FROM gmail_draft_operations')]
            return {'packet_id':packet['packet_id'],'job_id':packet['job_id'],'application_id':application['id'],'adapter_calls':len(fake.calls),'operations':operations}
        @app.post('/__r2/restrict-lead')
        def restrict_lead():
            with db.transaction() as c:c.execute("UPDATE jobs SET canonical_application_url='https://linkedin.com/jobs/view/123'")
            return {'isolated':True}
        @app.post('/__r2/shutdown')
        def shutdown():
            threading.Timer(.1,lambda:setattr(server,'should_exit',True)).start();return {'isolated':True}
        server.run()


if __name__=='__main__':main()

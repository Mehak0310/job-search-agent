"""Isolated API/worker/SQLite server for R1 Playwright, without real accounts."""
import hashlib,json,subprocess,sys,tempfile,threading,re
from pathlib import Path
from unittest.mock import patch
import uvicorn
from job_agent.database import Database,now
from job_agent.main import create_app
from job_agent.models import JobInput
from job_agent.service import JobService
from job_agent.m2d import M2DEngine
from job_agent.m2d_models import OperationalFacts
from job_agent.m3 import M3Engine
from job_agent.browser_workers import BrowserWorkers
from job_agent import browser_applications as runner


def main():
    with tempfile.TemporaryDirectory(prefix='job-agent-r1-') as temporary:
        root=Path(temporary);db=Database(root/'fixture.sqlite3');service=JobService(db);__import__('tests.synthetic_profile',fromlist=['seed']).seed(db);processes=[];held=False
        with db.transaction() as conn:
            profile=json.loads(conn.execute('SELECT config FROM candidate_profiles_v2').fetchone()[0]);profile['skill_evidence']={s:[{'source':'explicit synthetic accepted fact'}] for s in ['react','typescript']};conn.execute('UPDATE candidate_profiles_v2 SET config=?',(json.dumps(profile),))
        resume=root/'synthetic.pdf';resume.write_bytes(b'%PDF-1.4 synthetic fixture only')
        (root/'documents').mkdir();(root/'documents/manifest.json').write_text(json.dumps({'documents':[{'canonical_name':'Resume.pdf','local_path':str(resume),'sha256':hashlib.sha256(resume.read_bytes()).hexdigest(),'status':'synthetic approved fixture'}]}))
        def seed(offset=0):
            for index in range(5):
                service.import_rows([JobInput(source='r1-synthetic',source_job_id=str(offset+index),company='R1 Fixture '+str(offset+index),title='R1 Frontend '+str(index),location='Noida, India',work_mode='hybrid',description='Requirements\nReact and TypeScript are required.\nResponsibilities\nBuild accessible frontend components. '*8,skills=['react','typescript'],application_url='https://job-boards.greenhouse.io/r1-fixture/jobs/'+str(1000+offset+index),is_sample=True)])
            engine=M2DEngine(db)
            with db.transaction() as conn:
                jobs=[dict(r) for r in conn.execute('SELECT * FROM jobs')]
            for job in jobs:
                engine.set_operational_state(job['id'],OperationalFacts(active='PASS',india_eligible='PASS',headcount='PASS',direct_permanent_payroll='PASS',mandatory_requirements='PASS',work_mode='hybrid'),job_id=job['id'])
                stamp=now()
                with db.transaction() as conn:
                    conn.execute('UPDATE source_references SET listing_url=?,last_seen=?,imported_at=? WHERE job_id=?',(job['application_url'],stamp,stamp,job['id']))
                    conn.execute('UPDATE jobs SET required_skills=?,required_experience_min=NULL,required_experience_max=NULL,match_score=? WHERE id=?',(json.dumps(['react','typescript']),[80,99,75,90,85][int(job['title'][-1])] if job['title'][-1].isdigit() else 99,job['id']))
                    detail={'requirements_source':{'content_status':'FULL','source_url':job['application_url'],'description_sha256':hashlib.sha256(job['description'].encode()).hexdigest(),'retrieval_version':'r1-isolated-fixture','verified_at':stamp}}
                    from job_agent.requirement_clauses import inventory
                    observed=inventory({**job,'discovery_detail':detail})
                    detail['requirements_source']['nonmandatory_reviews']=[{'clause_id':c['id'],'source_excerpt':c['excerpt'],'source_hash':observed['source_hash'],'classification':'INFORMATIONAL','reviewer':'isolated fixture reviewer','evidence_ref':'fixture:responsibility-review'} for c in observed['clauses'] if c['excerpt'].startswith('Build accessible frontend components.')]
                    conn.execute('UPDATE jobs SET discovery_detail=? WHERE id=?',(json.dumps(detail),job['id']))
                for kind,factual in (
                    ('active','Vacancy is active and open for applications.'),
                    ('india_eligible','Employer explicitly supports employment in India.'),
                    ('headcount','Global workforce of 5,000 employees.'),
                    ('direct_permanent_payroll','India employees are hired directly on permanent full-time payroll.'),
                ):
                    engine.record_evidence(job['id'],kind,'PASS',factual=factual,evidence_url=job['application_url'],verified_at=stamp)
                M3Engine(db).prepare(job['id'])
        seed();app=create_app(db.path)
        @app.get('/__r1/priority-evidence')
        def priority_evidence():
            with db.transaction() as conn:
                queue=[dict(r) for r in conn.execute('SELECT job_id,fit,reserved_order,eligibility,batch_id FROM application_priority WHERE batch_id IS NOT NULL ORDER BY reserved_order')]
                events=[json.loads(r[0]) for r in conn.execute("SELECT details FROM browser_worker_events WHERE event='PRIORITY_SELECTED' ORDER BY id")]
            return {'queue':queue,'worker_selection':events}
        def launch(db,batch_id,allow_upload=True,only_application=None):
            workers=BrowserWorkers(db);ids=[r['id'] for r in runner.BrowserStore(db).list(batch_id)]
            operation=workers.enqueue('PREPARE',ids,batch_id)
            arguments=[sys.executable,'-m','tests.r1_fixture_worker','--db',str(db.path),'--batch',batch_id,'--workflow',operation]
            if held:arguments.append('--hold')
            log=(root/'worker.log').open('ab');process=subprocess.Popen(arguments,stdin=subprocess.DEVNULL,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));log.close();processes.append(process);workers.attach_pid(operation,process.pid);return process.pid
        original_switch=runner.switch_tab
        def switch(db,identifier):
            def absent():raise OSError('Synthetic session loss')
            with patch.object(runner,'browser_metadata',absent):return original_switch(db,identifier)
        runner.launch_worker=launch;runner.switch_tab=switch
        @app.post('/__r1/hold-next')
        def hold_next():
            nonlocal held
            held=True;seed(10);return {'fixture_only':True}
        def stop_fixture_worker(process):
            if process.poll() is not None:return
            # This Popen object belongs exclusively to this disposable fixture.
            # Popen.kill uses the owned process handle on Windows; external taskkill
            # may be denied even when this parent is allowed to terminate its child.
            process.kill();process.wait(timeout=5)
        @app.post('/__r1/terminate-worker')
        def terminate():
            process=processes[-1]
            stop_fixture_worker(process)
            return {'fixture_only':True,'terminated':True}
        @app.get('/__r1/evidence')
        def evidence():
            with db.transaction() as conn:
                return {'fixture_only':True,'schema':conn.execute('PRAGMA user_version').fetchone()[0],'events':conn.execute('SELECT count(*) FROM browser_worker_events').fetchone()[0],'drafts':conn.execute('SELECT count(*) FROM gmail_draft_operations').fetchone()[0],'submitted_jobs':conn.execute("SELECT count(*) FROM jobs WHERE status='SUBMITTED'").fetchone()[0]}
        @app.post('/__r1/unsupported-requirement')
        def unsupported():
            service.import_rows([JobInput(source='r1-synthetic',source_job_id='unsupported',company='R1 Unsupported',title='R1 Unsupported Requirement',location='Noida, India',work_mode='hybrid',description='Requirements\nReact required.\nResponsibilities\nOnly graduates are considered.',skills=['unsupported-fixture-capability'],application_url='https://job-boards.greenhouse.io/r1-fixture/jobs/1099',is_sample=True)])
            with db.transaction() as conn:
                job=conn.execute("SELECT id FROM jobs WHERE company='R1 Unsupported'").fetchone()[0]
                conn.execute("UPDATE jobs SET required_skills=?,required_experience_min=NULL,required_experience_max=NULL WHERE id=?",(json.dumps(['react']),job))
                current=dict(conn.execute('SELECT * FROM jobs WHERE id=?',(job,)).fetchone())
                detail={'requirements_source':{'content_status':'FULL','source_url':current['application_url'],'description_sha256':hashlib.sha256(current['description'].encode()).hexdigest(),'retrieval_version':'r1-isolated-fixture','verified_at':now()}}
                conn.execute('UPDATE jobs SET discovery_detail=? WHERE id=?',(json.dumps(detail),job))
            engine=M2DEngine(db);engine.set_operational_state(job,OperationalFacts(active='PASS',india_eligible='PASS',headcount='PASS',direct_permanent_payroll='PASS'),job_id=job)
            engine.enqueue(kind='VERIFICATION',source_id=None,stream='PIPELINE',category='MANDATORY_REQUIREMENTS',job_key=job,payload={'fact':'mandatory_requirements'})
            engine.execute_verification_tasks(1)
            with db.transaction() as conn:
                assessment=conn.execute('SELECT state FROM requirement_assessments WHERE job_id=? ORDER BY created_at DESC LIMIT 1',(job,)).fetchone()
            return {'fixture_only':True,'job_id':job,'requirement_state':assessment['state']}
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=8017,log_level='warning'))
        @app.post('/__r1/shutdown')
        def shutdown():
            threading.Timer(.1,lambda:setattr(server,'should_exit',True)).start();return {'fixture_only':True}
        try:server.run()
        finally:
            for process in processes:
                stop_fixture_worker(process)


if __name__=='__main__':main()

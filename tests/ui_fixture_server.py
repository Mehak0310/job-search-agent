"""Disposable localhost UI server for complete source-checkout regression."""
import tempfile
import threading
from pathlib import Path
import uvicorn
from job_agent.main import create_app
from tests.synthetic_profile import seed
from job_agent.models import JobInput
from job_agent.service import JobService
from job_agent.m2d import M2DEngine
from job_agent.m3 import M3Engine


def seed_packet(db):
    """Provide a fictional packet so populated editor assertions never skip."""
    service=JobService(db)
    service.import_rows([JobInput(source='ui-fixture',source_job_id='role',company='UI Example',
        title='Frontend Fixture Engineer',location='India',work_mode='remote',
        description='Fictional React and TypeScript component role',skills=['react','typescript'],
        application_url='https://example.com/fixture-role',is_sample=True)])
    engine=M2DEngine(db);engine.seed();engine.sync_existing_jobs()
    with db.transaction() as conn:
        key=conn.execute("SELECT s.job_key FROM job_operational_state s JOIN jobs j ON j.id=s.job_id WHERE j.company='UI Example'").fetchone()[0]
    M3Engine(db).prepare(key)


def main():
    with tempfile.TemporaryDirectory(prefix='job-agent-ui-') as folder:
        app=create_app(Path(folder)/'fixture.sqlite3')
        seed(app.state.service.db)
        seed_packet(app.state.service.db)
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=8019,
                    loop='job_agent.server_runtime:new_server_loop'))
        @app.post('/__ui/shutdown')
        def shutdown():
            threading.Timer(.1,lambda:setattr(server,'should_exit',True)).start()
            return {'fixture_only':True}
        server.run()


if __name__=='__main__':main()

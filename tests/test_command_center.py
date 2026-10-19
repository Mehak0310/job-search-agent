from job_agent.database import Database
from job_agent.command_center import inbox, runs
from job_agent.registry import Registry


def test_read_only_received_order_and_no_alert_promotion(tmp_path):
    db = Database(tmp_path / 'test.sqlite3')
    with db.transaction() as conn:
        conn.executemany('INSERT INTO email_message_metadata VALUES(?,?,?,?)', [('alert','noreply@example.com','Jobs','2026-10-19'),('action','recruiter@example.com','Interview','2026-10-18')])
        conn.executemany('INSERT INTO message_priority VALUES(?,?,?,?,?,?)', [('alert','AUTOMATED_JOB_ALERT',0,None,'Automated alert','fixture'),('action','INTERVIEW_REQUEST',3,'2026-10-20','Reply requested','fixture')])
        before = conn.total_changes
    result = inbox(db)
    assert [r['message_id'] for r in result['items']] == ['action','alert']
    assert result['items'][1]['category'] == 'AUTOMATED_JOB_ALERT'
    assert result['items'][0]['gmail_url'].endswith('/action')
    assert before == 4
    assert runs(db)['items'] == []
    assert Registry(db).list() == []


def test_source_projection_reports_actual_counts_and_latest_run(tmp_path):
    from job_agent.discovery_models import DiscoveryConfig, SourceConfig
    db = Database(tmp_path / 'test.sqlite3')
    registry = Registry(db)
    registry.seed(DiscoveryConfig(sources=[SourceConfig(id='fixture',provider='greenhouse',company='Example',board='example')]))
    with db.transaction() as conn:
        conn.execute("INSERT INTO discovery_runs VALUES('run','COMPLETED','2026-10-19',NULL,NULL,'{}',NULL)")
        conn.execute("INSERT INTO discovery_source_runs VALUES('run','fixture','SUCCESS','2026-10-19',NULL,NULL,'{\"new_jobs\":2}',NULL)")
    row = registry.list()[0]
    assert row['retained_job_count'] == 0
    assert row['last_run_metrics'] == {'new_jobs':2}
    assert runs(db)['items'][0]['sources'][0]['source_id'] == 'fixture'


def test_projection_endpoints_are_read_only(tmp_path):
    from fastapi.testclient import TestClient
    from job_agent.main import create_app
    app = create_app(tmp_path / 'test.sqlite3')
    db = app.state.service.db
    with db.transaction() as conn:
        counts = {name:conn.execute('SELECT COUNT(*) FROM '+name).fetchone()[0] for name in ['jobs','status_history','gmail_draft_operations','browser_applications']}
    with TestClient(app) as client:
        assert client.get('/api/inbox/messages').json()['items'] == []
        assert client.get('/api/activity/runs').json()['items'] == []
        assert client.get('/api/sources').status_code == 200
    with db.transaction() as conn:
        assert counts == {name:conn.execute('SELECT COUNT(*) FROM '+name).fetchone()[0] for name in counts}

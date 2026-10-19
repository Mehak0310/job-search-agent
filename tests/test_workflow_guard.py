import subprocess
import sys

import pytest

from job_agent.workflow_guard import workflow_lease
from job_agent.discovery_models import DiscoverySettings
from job_agent.gmail_local import GmailDraftAdapter
from job_agent.m3 import M3Engine


def test_live_process_cannot_overlap_and_stale_file_is_harmless(tmp_path):
    path = tmp_path / 'state.sqlite3'
    code = ('from job_agent.workflow_guard import workflow_lease; '
            'import sys; '
            '\nwith workflow_lease(sys.argv[1]): pass')
    with workflow_lease(path):
        result = subprocess.run([sys.executable, '-c', code, str(path)], capture_output=True, text=True)
        assert result.returncode != 0
        assert 'workflow_already_running' in result.stderr
    # The old lock file remains, but the released kernel lease allows restart.
    with workflow_lease(path):
        pass


def test_exception_releases_workflow_lease(tmp_path):
    path = tmp_path / 'state.sqlite3'
    with pytest.raises(RuntimeError):
        with workflow_lease(path):
            raise RuntimeError('isolated failure')
    with workflow_lease(path):
        pass


def test_direct_backend_and_adapter_writes_disabled_before_side_effects(tmp_path):
    # No database or credentials are needed to enforce the release boundary.
    with pytest.raises(ValueError, match='external_writes_disabled'):
        M3Engine(None, tmp_path/'manifest.json').create_draft('untrusted', None, object())
    adapter = GmailDraftAdapter(tmp_path/'client.json', tmp_path/'token.json')
    with pytest.raises(ValueError, match='external_writes_disabled'):
        adapter.create_draft(to='person@example.com', subject='x', text='x', html='x')
    assert not list(tmp_path.iterdir())


def test_retry_configuration_cannot_exceed_two_retries():
    with pytest.raises(ValueError):
        DiscoverySettings(retry_limit=3)


def test_failed_local_stage_is_checkpointed_and_healthy_stage_continues(tmp_path):
    import json
    from job_agent.database import Database
    from job_agent.release import _local_stage
    db=Database(tmp_path/'state.sqlite3')
    with db.transaction() as conn:
        conn.execute("INSERT INTO workflow_runs(run_id,status,started_at,stage_results,resume_command) VALUES('fixture','RUNNING','2026-10-17','{}','fixture')")
    results={}
    def fail():
        raise ValueError('private-token-never-record-this')
    _local_stage(db,'fixture',results,'broken',fail)
    _local_stage(db,'fixture',results,'healthy',lambda:{'recovered':1})
    with db.transaction() as conn:
        stored=conn.execute("SELECT stage_results,error_count FROM workflow_runs WHERE run_id='fixture'").fetchone()
    assert stored['error_count']==1 and 'private-token' not in stored['stage_results']
    assert json.loads(stored['stage_results'])['healthy']['recovered']==1
    # Restart does not erase failure history or blindly retry it.
    _local_stage(db,'fixture',results,'broken',lambda:pytest.fail('unexpected retry'))
    assert results['broken']['status']=='FAILED' and results['broken']['retry_condition']

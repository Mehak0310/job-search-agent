"""Production regressions reproduced using synthetic SQLite and browser doubles."""
import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from job_agent import browser_applications as runner
from job_agent.browser_store import BrowserStore
from job_agent.browser_workers import fair_applications
from job_agent.priority_queue import refresh, candidates
from job_agent.review_workflow import progress
from tests.test_browser_applications import prepared_store
from tests.test_priority_queue import jobs


def test_batch_accounts_for_submitted_and_awaiting_inspection(tmp_path):
    db, _, ids = jobs(tmp_path)
    store = BrowserStore(db)
    batch = store.batch(limit=5)
    apps = batch['applications']
    for app, state in zip(apps, ['SESSION_LOST', 'ERROR', 'NEEDS_EMPLOYER_CHECK', 'AWAITING_INSPECTION', 'USER_REPORTED_SUBMITTED']):
        store.update(app['id'], state=state)
    current = progress(db)['batches'][0]
    assert current['submitted'] == 1
    assert current['agent_checks'] == 4
    assert current['preparing'] == 0
    assert sum(current[k] for k in ['submitted', 'agent_checks', 'ready', 'needs_answers', 'preparing']) == 5


def test_sync_does_not_spend_slots_on_submitted_history(tmp_path):
    store, _, key = prepared_store(tmp_path)
    app = store.batch([key], 1)['applications'][0]
    store.update(app['id'], state='USER_REPORTED_SUBMITTED')
    assert fair_applications(store.db) == []


def test_closed_vacancy_is_removed_before_five_slots_are_selected(tmp_path):
    db, _, ids = jobs(tmp_path)
    with db.transaction() as c:
        c.execute("UPDATE jobs SET activity_status='CLOSED' WHERE id=?", (ids[0],))
    refresh(db)
    assert len(candidates(db)) == 5
    assert ids[0] not in [r['job_id'] for r in candidates(db)]
    assert BrowserStore(db).batch(limit=5)['selected'] == 5


def test_prepared_requisition_alias_does_not_consume_a_new_batch_slot(tmp_path):
    db, _, ids = jobs(tmp_path, (99, 95, 90, 85, 80, 75, 70))
    store = BrowserStore(db)
    prior = store.batch([ids[0]], 1)
    store.update(prior['applications'][0]['id'], state='NEEDS_USER_ANSWER')
    with db.transaction() as c:
        c.execute("UPDATE browser_batches SET status='REVIEW' WHERE id=?", (prior['batch_id'],))
        original=c.execute('SELECT application_url FROM jobs WHERE id=?', (ids[0],)).fetchone()[0]
        c.execute('UPDATE jobs SET canonical_application_url=? WHERE id=?', (original, ids[1]))
    refresh(db)
    assert ids[1] not in [r['job_id'] for r in candidates(db)]
    assert store.batch(limit=5)['selected'] == 5


def test_switch_rebinds_recovered_target_and_returns_current_health(tmp_path, monkeypatch):
    store, _, key = prepared_store(tmp_path)
    app = store.batch([key], 1)['applications'][0]
    store.update(app['id'], state='SESSION_LOST')
    page = SimpleNamespace(bring_to_front=lambda: None)
    calls = []
    @contextmanager
    def connection():
        def connect(url, **kwargs):
            calls.append(kwargs)
            return object()
        yield SimpleNamespace(chromium=SimpleNamespace(connect_over_cdp=connect))
    monkeypatch.setattr('playwright.sync_api.sync_playwright', connection)
    monkeypatch.setattr(runner, 'browser_metadata', lambda: {'webSocketDebuggerUrl':'ws://local/new-session'})
    monkeypatch.setattr(runner, 'recover_page', lambda *args: page)
    monkeypatch.setattr(runner, 'target_id', lambda p: 'recovered-target')
    result = runner.switch_tab(store.db, app['id'])
    assert result['state'] == 'TAB_SELECTED'
    assert store.get(app['id'])['target_id'] == 'recovered-target'
    assert store.get(app['id'])['session_health'] == 'CONNECTED'
    assert calls[0]['timeout'] <= 10000


def test_switch_browser_failure_is_actionable_and_preserves_progress(tmp_path, monkeypatch):
    from playwright.sync_api import TimeoutError
    store, _, key = prepared_store(tmp_path)
    app = store.batch([key], 1)['applications'][0]
    store.update(app['id'], state='NEEDS_USER_ANSWER', missing=['A saved question'])
    @contextmanager
    def connection():
        def connect(*args, **kwargs):raise TimeoutError('private websocket detail')
        yield SimpleNamespace(chromium=SimpleNamespace(connect_over_cdp=connect))
    monkeypatch.setattr('playwright.sync_api.sync_playwright', connection)
    monkeypatch.setattr(runner, 'browser_metadata', lambda: {})
    with pytest.raises(ValueError, match='Browser connection timed out'):
        runner.switch_tab(store.db, app['id'])
    assert json.loads(store.get(app['id'])['missing']) == ['A saved question']

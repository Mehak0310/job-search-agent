"""Recovery must inspect existing tabs, preserve reports and never infer submission."""
import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from job_agent import browser_applications as runner
from tests.test_browser_applications import prepared_store, frame, browser


def connected(monkeypatch, browser, page):
    @contextmanager
    def connection():
        yield SimpleNamespace(chromium=SimpleNamespace(connect_over_cdp=lambda url,**kwargs: browser))
    monkeypatch.setattr('playwright.sync_api.sync_playwright', connection)
    monkeypatch.setattr(runner, 'browser_metadata', lambda: {'webSocketDebuggerUrl':'ws://local/session'})
    monkeypatch.setattr(runner, 'recover_page', lambda b, item: page)
    monkeypatch.setattr(runner, 'target_id', lambda p: 'existing-target')


@pytest.mark.parametrize('markup,state', [
    ('<div id="application_confirmation">Thank you for applying</div>', 'SUBMISSION_CONFIRMED'),
    ('<div id="application_confirmation" hidden>Thank you for applying</div>', 'SESSION_LOST'),
    ('<div class="confirmation">Application submitted</div>', 'SESSION_LOST'),
    ('<div id="application_confirmation">Application submitted</div><div class="application-confirmation">Application submitted</div>', 'SESSION_LOST'),
])
def test_confirmation_requires_unique_visible_supported_evidence(tmp_path, monkeypatch, frame, browser, markup, state):
    store, _, key = prepared_store(tmp_path)
    app = store.batch([key], 1)['applications'][0]
    frame.set_content(markup)
    connected(monkeypatch, browser, frame)
    runner.reinspect(store.db, app['id'])
    current = store.get(app['id'])
    assert current['state'] == state
    assert bool(current['confirmation_ref']) == (state == 'SUBMISSION_CONFIRMED')
    if state == 'SUBMISSION_CONFIRMED':
        assert current['confirmation_ref'].startswith('browser-confirmation:')
        assert (runner.root_for(store.db)/(app['id']+'-confirmation.png')).is_file()
    assert frame.is_closed() is False


def test_reinspection_reads_required_fields_and_never_checks_attestation(tmp_path, monkeypatch, frame, browser):
    store, _, key = prepared_store(tmp_path)
    app = store.batch([key], 1)['applications'][0]
    connected(monkeypatch, browser, frame)
    frame.set_content('<form><label>Name<input id="n" required value="Synthetic"></label><fieldset><legend>Work authorization</legend><label>Yes<input type="radio" name="auth" required checked></label><label>No<input type="radio" name="auth" required></label></fieldset><label>Legal attestation<input id="legal" type="checkbox" required></label></form>')
    runner.reinspect(store.db, app['id'])
    current = store.get(app['id'])
    assert current['state'] == 'NEEDS_USER_ANSWER'
    assert json.loads(current['missing']) == ['Legal attestation']
    assert not frame.locator('#legal').is_checked()
    frame.locator('#legal').check()  # Simulated human decision, outside runner.
    runner.reinspect(store.db, app['id'])
    assert store.get(app['id'])['state'] == 'NEEDS_EMPLOYER_CHECK'
    assert 'headcount' in json.loads(store.get(app['id'])['checks'])


def test_missing_tab_and_unsupported_confirmation_preserve_manual_history(tmp_path, monkeypatch, frame, browser):
    store, _, key = prepared_store(tmp_path)
    app = store.batch([key], 1)['applications'][0]
    connected(monkeypatch, browser, frame)
    store.update(app['id'], state='USER_REPORTED_SUBMITTED')
    frame.set_content('<p>Thanks for visiting</p>')
    runner.reinspect(store.db, app['id'])
    current = store.get(app['id'])
    assert current['state'] == 'USER_REPORTED_SUBMITTED' and not current['confirmation_ref']
    monkeypatch.setattr(runner, 'recover_page', lambda *args: None)
    assert runner.switch_tab(store.db, app['id'])['state'] == 'SESSION_LOST'
    assert store.get(app['id'])['state']=='USER_REPORTED_SUBMITTED'
    assert store.get(app['id'])['session_health']=='LOST'
    assert not frame.is_closed()


def test_controller_finishes_error_without_closing_browser(tmp_path, monkeypatch, frame, browser):
    store, _, key = prepared_store(tmp_path)
    batch = store.batch([key], 1)
    connected(monkeypatch, browser, frame)
    monkeypatch.setattr(runner, 'ensure_browser', lambda db: {})
    def parser_defect(*args):
        raise ValueError('unsupported form')
    monkeypatch.setattr(runner, 'prepare_one', parser_defect)
    result = runner.execute_batch(store.db, batch['batch_id'], False, batch['applications'][0]['id'])
    assert result[0]['state'] == 'ERROR'
    with store.db.transaction() as conn:
        assert conn.execute('SELECT status FROM browser_batches').fetchone()[0] == 'REVIEW'
    assert browser.is_connected() and not frame.is_closed()


def test_sync_refreshes_saved_answers_only_without_uploads(tmp_path, monkeypatch):
    store, _, key = prepared_store(tmp_path)
    batch = store.batch([key], 1); app = batch['applications'][0]
    store.update(app['id'], state='NEEDS_USER_ANSWER')
    monkeypatch.setattr(runner, 'ensure_browser', lambda db: {})
    monkeypatch.setattr(runner, 'reinspect', lambda db, identifier: None)
    monkeypatch.setattr(runner, 'approved_facts', lambda db: ({'version':3}, {}, {}, {}))
    calls = []
    @contextmanager
    def synthetic_connection():yield object()
    monkeypatch.setattr(runner,'browser_connection',synthetic_connection)
    monkeypatch.setattr(runner,'browser_metadata',lambda:{})
    def prepared(store,item,browser,metadata,allow_upload):
        calls.append((item['batch_id'],allow_upload,item['id']))
        store.update(item['id'],state='NEEDS_EMPLOYER_CHECK')
    monkeypatch.setattr(runner,'prepare_one',prepared)
    assert runner.synchronize(store.db, app['id'])['state'] == 'SYNCHRONIZED'
    assert calls == [(batch['batch_id'], False, app['id'])]
    assert store.get(app['id'])['state'] == 'NEEDS_EMPLOYER_CHECK'
    store.update(app['id'],state='PREPARING')
    runner.synchronize(store.db, app['id'])
    assert len(calls) == 1  # A busy preparation cannot spawn a nested controller.


def test_sync_failed_eligibility_is_agent_owned_not_personal_question(tmp_path, monkeypatch):
    store, _, key = prepared_store(tmp_path)
    app = store.batch([key], 1)['applications'][0]
    store.update(app['id'], state='NEEDS_USER_ANSWER')
    monkeypatch.setattr(runner, 'ensure_browser', lambda db: {})
    def incompatible(*args):
        raise ValueError('incompatible_known_office_location')
    monkeypatch.setattr(runner, 'reinspect', incompatible)
    runner.synchronize(store.db, app['id'])
    current = store.get(app['id'])
    assert current['state'] == 'ERROR' and json.loads(current['missing']) == []
    assert 'eligibility' in json.loads(current['checks'])[0]

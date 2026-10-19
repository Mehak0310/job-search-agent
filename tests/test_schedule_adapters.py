import pytest
from job_agent.database import Database
from job_agent.schedule_adapters import assemble
from job_agent import orchestration as o


def test_existing_local_adapters_and_disabled_plans(tmp_path,monkeypatch):
    db=Database(tmp_path/'state.sqlite3');config=tmp_path/'discovery.json'
    config.write_text('{"sources":[]}')
    adapters=assemble(db,config)
    assert set(adapters)==o.STAGES
    assert adapters['DISCOVERY']('fixture')['metrics']['requests']==0
    assert adapters['VERIFICATION']('fixture')['attempted']==0
    assert adapters['NOTIFICATIONS']('fixture')=={'inspected':0}
    with pytest.raises(ValueError,match='authorized_reader'):adapters['GMAIL_INTAKE']('fixture')
    with pytest.raises(ValueError,match='explicit_runtime_permission'):adapters['PREPARATION']('fixture')
    assert assemble(db,config,allow_browser=True)['PREPARATION']('fixture')['selected']==0
    for stage in o.STAGES:o.schedule_plan(db,stage,3600,'2026-10-01T00:00:00+00:00')
    assert o.run_scheduled(db,adapters,approval_reference='isolated fixture')==[]
    assert all(not row['enabled'] for row in o.schedules(db)['items'])


def test_gmail_adapter_requires_configured_interval_and_retains_budget(tmp_path,monkeypatch):
    db=Database(tmp_path/'state.sqlite3');calls=[];reader=object()
    def ingest(worker,received,start,end,max_pages):
        calls.append((received,start,end,max_pages));return {'fixture':True,'status':'COMPLETED'}
    monkeypatch.setattr('job_agent.gmail_local.ingest_live_interval',ingest)
    adapters=assemble(db,tmp_path/'unused.json',gmail_reader=reader,gmail_interval=lambda:('start','end'))
    assert adapters['GMAIL_INTAKE']('fixture')=={'fixture':True,'status':'COMPLETED'}
    assert calls==[(reader,'start','end',5)]


def test_uncertain_preparation_schedule_never_retries(tmp_path):
    db=Database(tmp_path/'state.sqlite3')
    o.schedule_plan(db,'PREPARATION',60,'2026-10-01T00:00:00+00:00')
    with db.transaction() as c:c.execute('UPDATE local_schedule_plans SET enabled=1')
    def timeout(key):raise TimeoutError()
    assert o.run_scheduled(db,{'PREPARATION':timeout},approval_reference='fixture')[0]['state']=='UNCERTAIN'
    assert o.run_scheduled(db,{'PREPARATION':timeout},approval_reference='fixture')==[]

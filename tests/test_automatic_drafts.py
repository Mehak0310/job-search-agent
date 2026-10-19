import json
import pytest
from fastapi.testclient import TestClient
from job_agent.automatic_drafts import configure,process,status
from job_agent.runtime_policy import require_external_write,draft_payload
from tests.test_preparation_authorizations import setup_authorized


def fixture(tmp_path):
    db,engine,packet,_,_,_=setup_authorized(tmp_path)
    with db.transaction() as conn:conn.execute('UPDATE jobs SET is_sample=0')
    return db,engine,packet


class Adapter:
    def __init__(self,db,fail=False):self.db=db;self.calls=[];self.fail=fail
    def status(self):return {'live_ready':True}
    def create_draft(self,**kwargs):
        with self.db.transaction() as conn:assert conn.execute("SELECT state FROM gmail_draft_operations ORDER BY created_at DESC LIMIT 1").fetchone()[0]=='PENDING'
        require_external_write('gmail_draft',root=self.db.path.parent/'action-authorizations',authorization_id=kwargs['authorization_id'],target=kwargs['to'],payload_hash=draft_payload(to=kwargs['to'],subject=kwargs['subject'],text=kwargs['text'],html=kwargs['html']),consume=True)
        self.calls.append(kwargs)
        if self.fail:raise TimeoutError('synthetic')
        return {'id':'synthetic-unsent-draft','message':{'id':'synthetic-message'}}


@pytest.mark.parametrize('historical_policy',[False,True])
def test_r2_supersedes_standing_instruction_without_erasing_it(tmp_path,historical_policy):
    db,engine,packet=fixture(tmp_path);adapter=Adapter(db)
    if historical_policy:configure(db)
    result=process(db,engine=engine,adapter=adapter)
    assert result['saved']==0 and result['reason']=='exact_preview_approval_required'
    assert not status(db)['automatic_verified_drafts'] and status(db)['exact_approval_required']
    assert adapter.calls==[] and not hasattr(adapter,'send')
    if historical_policy:assert (db.path.parent/'gmail/draft-policy.json').is_file()


def test_http_historical_automatic_button_cannot_create_a_draft(tmp_path,monkeypatch):
    db,_,packet=fixture(tmp_path);configure(db);adapter=Adapter(db)
    from job_agent import main
    monkeypatch.setattr(main,'GmailDraftAdapter',lambda *args:adapter)
    with TestClient(main.create_app(db.path)) as client:
        assert client.get('/api/m3/gmail/status').json()['live_creation_enabled'] is False
        response=client.post('/api/m3/packets/'+packet['packet_id']+'/automatic-draft')
        assert response.status_code==200 and response.json()['saved']==0
        assert client.post('/api/m3/gmail/policy',json={'enabled':True}).status_code==404
    assert adapter.calls==[]

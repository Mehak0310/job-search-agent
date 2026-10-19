import json
from datetime import datetime,timedelta,timezone

import pytest

from job_agent.document_manifest import sha256,resolve_approved_document
from job_agent.m3_models import DraftRequest,PacketEdit
from job_agent.runtime_policy import issue_authorization,require_external_write,draft_payload
from tests.test_m3 import setup_engine,verified_contact


def setup_authorized(tmp_path):
    db,engine,key=setup_engine(tmp_path)
    manifest=json.loads(engine.manifest_path.read_text())
    for item in manifest['documents']:
        path=tmp_path/item['canonical_name'];path.write_bytes(b'isolated synthetic fixture')
        item.update(local_path=str(path),sha256=sha256(path))
    engine.manifest_path.write_text(json.dumps(manifest))
    packet=engine.prepare(key);contact=verified_contact(engine,key)
    packet=engine.get(packet['packet_id']);request=DraftRequest(contact_id=contact)
    root=db.path.parent/'action-authorizations';v=packet['version_data']
    payload=draft_payload(to='ria@example.com',subject=v['subject'],text=v['email_text'],html=v['email_html'])
    identifier=issue_authorization(root,operation='gmail_draft',target='ria@example.com',
        snapshot_hash=engine.draft_snapshot(packet['packet_id'],request),payload_hash=payload,user_reference='synthetic explicit authorization')
    return db,engine,packet,request.model_copy(update={'authorization_id':identifier}),root,payload


def test_scoped_backend_and_adapter_dispatch_once_with_durable_intent(tmp_path):
    db,engine,packet,request,root,payload=setup_authorized(tmp_path)
    class Adapter:
        def create_draft(self,**kwargs):
            # Durable pending intent exists before the external-write boundary.
            with db.transaction() as conn:
                assert conn.execute("SELECT state FROM gmail_draft_operations").fetchone()[0]=='PENDING'
            require_external_write('gmail_draft',root=root,authorization_id=kwargs['authorization_id'],
                target=kwargs['to'],payload_hash=payload,consume=True)
            return {'id':'isolated-draft'}
    assert engine.create_draft(packet['packet_id'],request,Adapter())['status']=='GMAIL_DRAFT_SAVED'
    with pytest.raises(ValueError,match='already_dispatched'):
        require_external_write('gmail_draft',root=root,authorization_id=request.authorization_id,
            target='ria@example.com',payload_hash=payload,consume=True)


@pytest.mark.parametrize('change',['packet','profile','document','recipient'])
def test_material_change_invalidates_authorization_before_journal(tmp_path,change):
    db,engine,packet,request,root,payload=setup_authorized(tmp_path)
    if change=='packet':
        v=packet['version_data'];engine.edit(packet['packet_id'],PacketEdit(subject='Changed subject',
            email_text=v['email_text'],email_html=v['email_html'],supporting_statement=v['supporting_statement']))
    elif change=='profile':
        with db.transaction() as conn:
            row=conn.execute('SELECT config FROM candidate_profiles_v2 WHERE id=1').fetchone()
            profile=json.loads(row[0]);profile['confirmed_facts']['notice_period']='changed'
            conn.execute('UPDATE candidate_profiles_v2 SET config=? WHERE id=1',(json.dumps(profile),))
    elif change=='document':
        (tmp_path/'Resume.pdf').write_bytes(b'changed actual bytes')
    else:
        with db.transaction() as conn:conn.execute("UPDATE contact_evidence SET email='other@example.com'")
    with pytest.raises(ValueError,match='mismatch'):
        engine.create_draft(packet['packet_id'],request,object())
    with db.transaction() as conn:assert conn.execute('SELECT count(*) FROM gmail_draft_operations').fetchone()[0]==0


def test_expired_or_forged_scope_and_sending_remain_blocked(tmp_path):
    _,_,_,request,root,payload=setup_authorized(tmp_path)
    with pytest.raises(ValueError,match='content_mismatch'):
        require_external_write('portal_upload',root=root,authorization_id=request.authorization_id,
                               target='ria@example.com',payload_hash=payload)
    path=root/(request.authorization_id+'.json');record=json.loads(path.read_text())
    record['expires_at']=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat();path.write_text(json.dumps(record))
    with pytest.raises(ValueError,match='expired'):
        require_external_write('gmail_draft',root=root,authorization_id=request.authorization_id,
                               target='ria@example.com',payload_hash=payload)
    for operation in ('send','submit','schedule'):
        with pytest.raises(ValueError,match='not_permitted'):
            issue_authorization(root,operation=operation,target='x',snapshot_hash='x',payload_hash='x',user_reference='fixture')


def test_missing_original_can_resolve_only_hash_identical_immutable_copy(tmp_path):
    root=tmp_path/'resumes';root.mkdir();original=tmp_path/'missing.pdf'
    temporary=root/'fixture';temporary.write_bytes(b'approved synthetic bytes');expected=sha256(temporary)
    path=root/(expected+'.pdf');temporary.rename(path)
    item=dict(local_path=str(original),canonical_name='Resume.pdf',sha256=expected)
    assert resolve_approved_document(item,tmp_path)==path
    original.write_bytes(b'new user version')
    with pytest.raises(ValueError,match='version_mismatch'):resolve_approved_document(item,tmp_path)

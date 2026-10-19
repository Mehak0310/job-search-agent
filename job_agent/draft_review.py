"""Immutable exact previews and serialized approval. R2 live creation is locked."""
import json
from .database import now
from .m3 import M3Engine
from .m3_models import DraftRequest
from .runtime_policy import digest,draft_payload,issue_authorization
from .workflow_guard import workflow_lease


def preview(db,packet_id,contact_id=None):
    engine=M3Engine(db);packet=engine.get(packet_id)
    if not packet:raise ValueError('packet_not_found')
    contact=next((c for c in packet['contacts'] if c['contact_id']==contact_id),None) if contact_id else next((c for c in packet['contacts'] if c['verification_status']=='VERIFIED'),None)
    blocks=[]
    with db.transaction() as conn:
        state=conn.execute('SELECT * FROM job_operational_state WHERE job_key=?',(packet['job_key'],)).fetchone()
        prior=conn.execute("SELECT state,gmail_draft_id FROM gmail_draft_operations WHERE job_key=? AND state IN ('PENDING','SAVED','UNCERTAIN') ORDER BY created_at DESC LIMIT 1",(packet['job_key'],)).fetchone()
    if not contact or contact['verification_status']!='VERIFIED' or not contact['email'] or not (contact['source_url'] or contact['source_message_id']):blocks.append('verified_role_recipient_required')
    elif not any(term in contact['role_relevance'].casefold() for term in ('recruit','talent','hiring','human resources','role contact')) or any(term in contact['email'].split('@')[0].casefold().replace('-','').replace('_','') for term in ('noreply','donotreply','privacy','support','security','notification','accessibility')):blocks.append('recipient_not_role_related')
    if state['readiness']=='EXCLUDED' or state['lifecycle']=='CLOSED':blocks.append('incompatible_job')
    for gate in ('active_state','india_state','headcount_state','payroll_state'):
        if state[gate]!='PASS':blocks.append(gate+':'+state[gate])
    if packet['requirement_assessment']['state']!='PASS':blocks.append('mandatory_requirements:'+packet['requirement_assessment']['state'])
    if packet['application_outcome']!='NOT_SUBMITTED':blocks.append('previous_submission_blocks_repeat')
    if prior:blocks.append('existing_draft_or_uncertain_operation')
    v=packet['version_data'];request=DraftRequest(contact_id=contact['contact_id']) if contact else None
    snapshot=None
    if request:
        try:snapshot=engine.draft_snapshot(packet_id,request)
        except ValueError:blocks.append('approved_documents_unavailable_or_changed')
    body=dict(packet_id=packet_id,contact_id=contact['contact_id'] if contact else None,recipient=contact['email'] if contact else None,
              recipient_evidence={'source_url':contact['source_url'],'message_id':contact['source_message_id'],'role_relevance':contact['role_relevance']} if contact else None,
              company=packet['company'],title=packet['title'],eligibility=packet['requirement_assessment']['state'],subject=v['subject'],text=v['email_text'],html=v['email_html'],
              attachment_policy='No automatic attachments. Review and attach only approved resume/profile card manually; never attach the private answer bank.',
              documents=packet['document_versions'],existing_operation=dict(prior) if prior else None,blockers=blocks,live_creation_enabled=False)
    payload=draft_payload(to=body['recipient'],subject=body['subject'],text=body['text'],html=body['html'])
    identifier=digest([body,snapshot,payload])
    with db.transaction() as conn:conn.execute('INSERT OR IGNORE INTO draft_previews VALUES(?,?,?,?,?,?,?)',(identifier,packet_id,body['contact_id'] or '',snapshot or '',payload,json.dumps(body),now()))
    return {'preview_id':identifier,**body}


def approve(db,identifier,adapter,*,approved=False):
    if approved is not True:raise ValueError('explicit_exact_draft_approval_required')
    # No API input, environment variable or historical standing instruction unlocks live Gmail.
    if getattr(adapter,'isolated_test_adapter',False) is not True:raise ValueError('r2_live_drafts_disabled_separate_post_verification_approval_required')
    with workflow_lease(db.path.parent/'gmail'/'exact-draft-review'):
        with db.transaction() as conn:row=conn.execute('SELECT * FROM draft_previews WHERE id=?',(identifier,)).fetchone()
        if not row:raise ValueError('draft_preview_not_found')
        current=preview(db,row['packet_id'],row['contact_id'])
        if current['blockers']:raise ValueError('draft_blocked:'+','.join(current['blockers']))
        if current['preview_id']!=identifier:raise ValueError('draft_preview_changed_review_again')
        with db.transaction() as conn:conn.execute('INSERT OR IGNORE INTO draft_approvals VALUES(?,?)',(identifier,now()))
        request=DraftRequest(contact_id=row['contact_id'])
        grant=issue_authorization(db.path.parent/'action-authorizations',operation='gmail_draft',target=current['recipient'],snapshot_hash=row['snapshot_hash'],payload_hash=row['payload_hash'],user_reference='Explicit exact draft approval '+identifier)
        result=M3Engine(db).create_draft(row['packet_id'],request.model_copy(update={'authorization_id':grant}),adapter)
        from urllib.parse import quote
        result['gmail_url']='https://mail.google.com/mail/u/0/#drafts/'+quote(result['gmail_draft_id'],safe='')
        return result

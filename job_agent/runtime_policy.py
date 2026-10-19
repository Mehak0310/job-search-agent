"""Exact-operation permissions under specs/security-and-approvals.md.

Only trusted local orchestration issues grants, never external content or API
inputs. Sending and submission are absent from permitted operations.
"""
import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from .workflow_guard import workflow_lease

PERMITTED_PREPARATION = {'gmail_draft', 'portal_fill', 'portal_upload'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False).encode()).hexdigest()


def draft_payload(*,to,subject,text,html,thread_message_id=None):
    return digest(dict(to=to,subject=subject,text=text,html=html,
                       thread_message_id=thread_message_id))


def issue_authorization(root, *, operation, target, snapshot_hash, payload_hash,
                        user_reference, lifetime_seconds=1800):
    """Local coordinator only; do not expose issuance through an HTTP endpoint."""
    if operation not in PERMITTED_PREPARATION:raise ValueError('operation_not_permitted')
    if not user_reference or not 1 <= lifetime_seconds <= 1800:raise ValueError('invalid_authorization')
    root=Path(root);root.mkdir(parents=True,exist_ok=True);identifier=uuid.uuid4().hex
    record=dict(authorization_id=identifier,operation=operation,target=target,
                snapshot_hash=snapshot_hash,payload_hash=payload_hash,
                user_reference=user_reference,state='READY',
                expires_at=(datetime.now(timezone.utc)+timedelta(seconds=lifetime_seconds)).isoformat())
    with (root/(identifier+'.json')).open('x',encoding='utf-8') as handle:json.dump(record,handle,sort_keys=True)
    return identifier


def require_external_write(operation, *, root=None, authorization_id=None,
                           target=None, snapshot_hash=None, payload_hash=None,consume=False):
    if operation not in PERMITTED_PREPARATION:raise ValueError('operation_not_permitted')
    from .policy_hooks import check
    check('external',operation)
    if root is None or not authorization_id:raise ValueError('external_writes_disabled_without_scoped_authorization')
    if not re.fullmatch('[0-9a-f]{32}',authorization_id):raise ValueError('invalid_authorization')
    root=Path(root)
    if not root.is_dir():raise ValueError('authorization_not_found')
    with workflow_lease(root/'authorization-state'):
        path=root/(authorization_id+'.json')
        try:
            if path.stat().st_size>16384:raise ValueError('invalid_authorization')
            record=json.loads(path.read_text(encoding='utf-8'))
        except (OSError,json.JSONDecodeError):raise ValueError('authorization_not_found') from None
        if record.get('state')!='READY':raise ValueError('authorization_already_dispatched')
        if datetime.fromisoformat(record['expires_at'])<=datetime.now(timezone.utc):raise ValueError('authorization_expired')
        expected=dict(operation=operation,target=target,payload_hash=payload_hash)
        if snapshot_hash is not None:expected['snapshot_hash']=snapshot_hash
        if any(record.get(key)!=value for key,value in expected.items()):raise ValueError('authorization_content_mismatch')
        if consume:
            record['state']='DISPATCHED'
            temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(record,sort_keys=True),encoding='utf-8');temporary.replace(path)
    return record

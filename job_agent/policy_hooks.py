"""Mandatory code-owned capability checks. Imported content never grants authority."""
from .preparation_policy import human_control

VERSION='mandatory-hooks-1'
ALLOWED={
    'form':frozenset({'FILL','SELECT','UPLOAD','NAVIGATE'}),
    'worker':frozenset({'PREPARE','SYNC'}),
    'research_worker':frozenset({'DISCOVERY','VERIFICATION','GMAIL_INTAKE'}),
    'external':frozenset({'gmail_draft','portal_fill','portal_upload'}),
    'scheduler':frozenset({'DISCOVERY','GMAIL_INTAKE','VERIFICATION','PREPARATION','NOTIFICATIONS'}),
}


def check(boundary,action,*,field=None,origin='runtime'):
    if origin!='runtime' or action not in ALLOWED.get(boundary,()):
        raise ValueError('policy_action_denied')
    if field is not None and human_control(field):
        raise ValueError('final_or_attestation_control_blocked')
    return VERSION


def grounded_fact(value,source,approved=False):
    return {'state':'PASS','value':value,'source':source} if approved and source and value is not None else {'state':'UNKNOWN','value':None,'source':None}


def compact_context(facts,keys,question,excerpt):
    """Only exact approved fields; no document bodies, tools, or model invocation."""
    selected={key:record for key,record in facts.items() if key in set(keys) and record.get('state')=='PASS' and record.get('source')}
    return {'policy_version':VERSION,'question':str(question)[:2000],
            'jd_excerpt':str(excerpt)[:6000],'facts':selected,'content_trust':'untrusted_data','llm_budget':0}

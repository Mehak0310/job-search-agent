"""Explicit local reconciliation; confirmations are private data, never defaults."""
from __future__ import annotations
import json
from pathlib import Path
from .candidate import CandidateProfile
from .models import key
from .resume_review import extract
from .document_manifest import resolve_approved_document, sha256
from .private_config import confirmation, document_for_role, document_role


def document_context(manifest_path: Path) -> dict:
    manifest=json.loads(manifest_path.read_text('utf-8'));result={}
    for item in manifest.get('documents', []):
        name=item.get('canonical_name')
        if not name or not document_role(item, manifest_path.parent.parent):continue
        if item.get('sha256'):
            path=resolve_approved_document(item,manifest_path.parent.parent)
        else:
            path=Path(item.get('local_path') or item.get('path') or '')
            if not path.is_file():continue
        result[name]={'version':str(item.get('version') or 'current'),'sha256':sha256(path),'sections':extract(path)}
    return result


def reconciled_profile(profile: CandidateProfile, manifest_path: Path, local_confirmation: dict | None = None):
    config=local_confirmation if local_confirmation is not None else confirmation(manifest_path.parent.parent)
    if not config.get('confirmation_reference') or not isinstance(config.get('updates'),dict):
        raise ValueError('explicit_local_confirmation_required')
    allowed={'candidate_name','home_location','total_experience_years','professional_ai_confirmed',
             'professional_ai_summary','professional_skills','technology_years','confirmed_facts','education'}
    if set(config['updates'])-allowed:raise ValueError('unsupported_confirmation_field')
    # Validate complete merged data before constructing revisions. This does not accept parser proposals.
    fields=profile.model_dump(mode='json');fields.update(config['updates'])
    validated=CandidateProfile.model_validate(fields)
    docs=document_context(manifest_path);reference=config['confirmation_reference'];evidence={}
    aliases={'llm inference/integration':['llm','large language model'],'git/github':['git','github'],
             'azure fundamentals':['azure'],'langchain text splitting':['langchain','text splitting'],
             'mcp-assisted sdd':['mcp','specification-driven']}
    for skill in validated.professional_skills:
        sources=[]
        for name,doc in docs.items():
            for ref,text in doc['sections']:
                if any(term in key(text) for term in aliases.get(skill,[skill])):
                    sources.append({'source':'document','document':name,'version':doc['version'],'reference':ref});break
        sources.append({'source':'user_confirmation','reference':reference,'scope':'professional skill'});evidence[skill]=sources
    facts=profile.confirmed_facts | validated.confirmed_facts
    provenance=dict(profile.fact_provenance)
    for fact in validated.confirmed_facts:
        provenance[fact]=[{'source':'user_confirmation','reference':reference,'scope':'explicit confirmation'}]
    manifest=json.loads(manifest_path.read_text('utf-8'))
    bank=document_for_role(manifest.get('documents',[]),'answer_bank',manifest_path.parent.parent)
    answer_doc=docs.get(bank['canonical_name']) if bank else None
    if answer_doc:
        for fact,terms in config.get('answer_terms',{}).items():
            if fact not in provenance:continue
            for ref,text in answer_doc['sections']:
                if all(term in key(text) for term in terms):
                    provenance[fact].append({'source':'approved_answer_bank','document':bank['canonical_name'],'version':answer_doc['version'],'reference':ref});break
    for fact in ('candidate_name','home_location','education','professional_ai_summary','technology_years'):
        if fact in config['updates']:provenance[fact]=[{'source':'user_confirmation','reference':reference,'scope':'explicit confirmation'}]
    documents={name:f"{doc['version']}:{doc['sha256']}" for name,doc in docs.items()}
    answers=dict(profile.approved_application_answers)
    answers.update({k:facts[k] for k in ('notice_period','expected_compensation','current_compensation','shift_preference') if k in validated.confirmed_facts})
    updated=validated.model_copy(update={'version':profile.version+1,'confirmed_facts':facts,'skill_evidence':evidence,
        'fact_provenance':provenance,'approved_application_answers':answers,'document_versions':profile.document_versions|documents,
        'background_established_skills':validated.professional_skills,
        'learning_skills':[s for s in profile.learning_skills if s not in config.get('remove_learning_skills',[])],'reviewed':False})
    return updated,{'documents':documents,'document_section_counts':{name:len(doc['sections']) for name,doc in docs.items()}}

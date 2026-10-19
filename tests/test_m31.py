from tests.synthetic_profile import confirmation
import json
from pathlib import Path
from docx import Document
from job_agent.candidate import CandidateProfile,display_skill
from job_agent.database import Database
from job_agent.profile_m31 import reconciled_profile
from job_agent.service import JobService

def documents(tmp_path):
    entries=[]
    for canonical,text in [("Resume.pdf","Angular React Python RAG FAISS fictional education"),("Answer_Bank.docx","Notice period 45 days. Expected compensation 42 LPA."),("Cover_letter.pdf","Application cover letter")]:
        path=tmp_path/(canonical.replace('.pdf','.docx'));doc=Document();doc.add_paragraph(text);doc.save(path)
        entries.append({"canonical_name":canonical,"path":str(path),"version":"synthetic","status":"approved"})
    manifest=tmp_path/'manifest.json';manifest.write_text(json.dumps({'documents':entries}),encoding='utf-8');return manifest

def test_reconciled_profile_professional_ai_scope_and_canonical_skills(tmp_path):
    profile,context=reconciled_profile(CandidateProfile(learning_skills=['langgraph','model training']),documents(tmp_path),confirmation())
    assert profile.professional_ai_confirmed and profile.technology_years['llm']==1 and profile.ai_employment_years is None
    assert profile.total_experience_years==8 and profile.technology_years['angular']==8 and profile.technology_years['react']==4
    assert 'langgraph' not in profile.learning_skills and 'model training' not in profile.learning_skills
    assert display_skill('fastapi')=='FastAPI' and display_skill('faiss')=='FAISS' and display_skill('.net core')=='.NET Core'
    assert profile.confirmed_facts['llm_experience'].endswith('not asserted')
    assert profile.approved_application_answers['current_compensation'].startswith('31 LPA')
    assert set(context['documents'])=={'Resume.pdf','Answer_Bank.docx','Cover_letter.pdf'}

def test_m31_revision_is_immutable_idempotent_and_profile_paths_agree(tmp_path):
    db=Database(tmp_path/'state.sqlite3');service=JobService(db);manifest=documents(tmp_path)
    first=service.apply_m31_profile(manifest,confirmation());second=service.apply_m31_profile(manifest,confirmation())
    assert first['changed'] and not second['changed']
    candidate=service.get_candidate_profile();search=service.get_profile();background=service.get_background()
    assert candidate['professional_ai_confirmed'] and set(candidate['professional_skills'])<=set(search['skills'])
    assert set(candidate['professional_skills'])<=set(background['established_skills'])
    assert candidate['resume_reviewed'] is False
    with db.transaction() as conn:
        assert conn.execute('pragma user_version').fetchone()[0]==17
        assert conn.execute('select count(1) from candidate_profile_revisions').fetchone()[0]==1
        try:conn.execute("update candidate_profile_revisions set reason='changed'")
        except Exception as error:assert 'immutable_profile_revision' in str(error)

def test_profile_api_exposes_human_skill_domains_and_resume_progress(client):
    data=client.get('/api/candidate-profile').json()
    assert set(data['skill_domains'])=={'Frontend and Architecture','AI Application Engineering','Backend and Data','Quality, Delivery and Leadership'}
    assert data['resume_proposals_pending']==0 and data['resume_display_name']==''

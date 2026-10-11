import io,sqlite3
from docx import Document
from job_agent.candidate import CandidateProfile
from job_agent.intelligence import SentenceTransformerProvider

def docx_bytes():
    document=Document();document.add_paragraph('Independent Project: RAG application with FastAPI and Python');document.add_paragraph('Master degree in Data Science');buffer=io.BytesIO();document.save(buffer);return buffer.getvalue()

def test_explicit_resume_parse_review_and_version(client):
    payload=docx_bytes();attached=client.post('/api/candidate-profile/resume',files={'file':('resume.docx',payload)});assert attached.status_code==200
    assert client.get('/api/candidate-profile/facts').json()==[]
    parsed=client.post('/api/candidate-profile/resume/parse');assert parsed.status_code==200 and parsed.json()['review_required']
    facts=client.get('/api/candidate-profile/facts').json();assert facts and all(x['status']=='PENDING' for x in facts)
    profile_before=client.get('/api/candidate-profile').json();skill=next(x for x in facts if x['category']=='SKILL_UNVERIFIED')
    assert client.patch('/api/candidate-profile/facts/'+skill['id'],json={'action':'ACCEPTED','reviewed_value':skill['value']}).json()['status']=='ACCEPTED'
    profile_after=client.get('/api/candidate-profile').json();assert profile_after['version']==profile_before['version']+1 and skill['value'] in profile_after['project_skills']
    education=next(x for x in facts if x['category']=='EDUCATION');assert client.patch('/api/candidate-profile/facts/'+education['id'],json={'action':'REJECTED'}).status_code==200
    assert client.patch('/api/candidate-profile/facts/'+education['id'],json={'action':'ACCEPTED'}).status_code==404

def test_resume_parse_requires_attachment(client):
    response=client.post('/api/candidate-profile/resume/parse');assert response.status_code==422 and response.json()['detail']=='resume_not_attached'

def test_v6_migration_backup_and_audit(app):
    db=app.state.service.db
    with db.transaction() as conn:assert conn.execute('pragma user_version').fetchone()[0]==6
    assert db.path.with_suffix(db.path.suffix+'.pre-v6.bak').exists()

def test_trained_provider_is_optional_and_offline():
    try:SentenceTransformerProvider(model_id='missing-local-model',local_files_only=True)
    except (ImportError,ModuleNotFoundError,OSError):pass

"""Fictional, explicitly injected test data; never used by production defaults."""
import json
from job_agent.candidate import CandidateProfile, SearchBackground, SKILL_DOMAINS


def profile(**updates):
    values=dict(candidate_name='Jordan Fixture',home_location='Sample City',total_experience_years=8,
                backend_experience_years=2,employment_skills=['angular','react','javascript','typescript','rest apis','.net','sql'],
                project_skills=['python','fastapi','rag','faiss','embeddings','ollama','automation'],
                preferred_locations=['noida','remote india'])
    values.update(updates)
    return CandidateProfile(**values)


def seed(db):
    with db.transaction() as conn:
        conn.execute('UPDATE candidate_profiles_v2 SET config=? WHERE id=1',(profile().model_dump_json(),))


def background(**updates):
    values=dict(total_years=8,backend_years=2,
                established_skills=['angular','react','javascript','typescript','rest apis'],
                developing_skills=['python','rag','langchain'])
    values.update(updates)
    return SearchBackground(**values)


def confirmation():
    return {'schema_version':1,'confirmation_reference':'explicit fictional fixture decision',
            'updates':profile(professional_ai_confirmed=True,
                professional_ai_summary=['Fictional local retrieval demonstration; no employer attribution.'],
                professional_skills=sorted({s for items in SKILL_DOMAINS.values() for s in items}|{'graphql'}),
                technology_years={'angular':8,'react':4,'llm':1},
                confirmed_facts={'llm_experience':'1 year; employer/client/production attribution not asserted',
                    'notice_period':'45 days; not serving','expected_compensation':'42 LPA; fixture preference',
                    'current_compensation':'31 LPA; fictional fixture'},
                education=['Fictional computing degree, Example University, 2018']).model_dump(
                    include={'candidate_name','home_location','total_experience_years','professional_ai_confirmed',
                    'professional_ai_summary','professional_skills','technology_years','confirmed_facts','education'}),
            'remove_learning_skills':['langgraph','model training']}

import json
from pathlib import Path
import pytest
from job_agent.candidate import CandidateProfile, SearchBackground
from job_agent.database import Database
from job_agent.service import JobService
from job_agent.private_config import local_configuration, confirmation, document_for_role, document_role
from job_agent.profile_m31 import reconciled_profile


def private_file(root, **values):
    path=root/'privacy-refactor'/'candidate-confirmations.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'schema_version':1,**values}))
    return path


def test_fresh_defaults_cannot_assert_private_candidate_facts():
    p=CandidateProfile()
    assert not p.candidate_name and not p.home_location
    assert p.total_experience_years is None and p.backend_experience_years==0
    assert not p.confirmed_facts and not p.professional_skills and not p.employment_skills
    assert not p.project_skills and not p.education and not p.technology_years
    assert not p.professional_ai_confirmed and not p.approved_application_answers
    assert SearchBackground().total_years==0
    assert p.search_background().total_years==0


def test_startup_retains_existing_profile_without_loading_or_approving_private_config(tmp_path):
    db=Database(tmp_path/'fixture.sqlite3');service=JobService(db)
    original=CandidateProfile(candidate_name='Casey Example',total_experience_years=4,
                              confirmed_facts={'fixture':'explicit accepted decision'})
    with db.transaction() as conn:
        conn.execute('UPDATE candidate_profiles_v2 SET config=?',(original.model_dump_json(),))
        before=conn.execute('SELECT config FROM candidate_profiles_v2').fetchone()[0]
    private_file(tmp_path,confirmation_reference='not invoked',updates={'candidate_name':'Different Fictional Name'})
    JobService(db)
    assert service.get_candidate_profile()['candidate_name']=='Casey Example'
    with db.transaction() as conn:
        assert conn.execute('SELECT config FROM candidate_profiles_v2').fetchone()[0]==before
        assert conn.execute('SELECT count(*) FROM candidate_profile_revisions').fetchone()[0]==0


def test_confirmation_absent_or_invalid_fails_closed(tmp_path):
    assert local_configuration(tmp_path)=={}
    with pytest.raises(ValueError,match='explicit_local_confirmation_required'):confirmation(tmp_path)
    path=private_file(tmp_path);path.write_text('invalid json')
    with pytest.raises(ValueError,match='private_confirmation_invalid'):local_configuration(tmp_path)
    path.write_text('[]')
    with pytest.raises(ValueError,match='private_confirmation_invalid'):local_configuration(tmp_path)


def test_manifest_roles_preserve_private_alias_and_fail_on_ambiguity(tmp_path):
    entry={'canonical_name':'Legacy_Fictional_File.pdf','sha256':'a'*64}
    private_file(tmp_path,document_roles={entry['canonical_name']:'resume'})
    before=dict(entry)
    assert document_for_role([entry],'resume',tmp_path)==entry and entry==before
    assert document_for_role([entry,{'canonical_name':'Resume.pdf'}],'resume',tmp_path) is None
    assert document_role({'canonical_name':'Resume.pdf','role':'invalid'},tmp_path) is None
    assert document_role({'canonical_name':'anything.pdf','role':'cover_letter'},tmp_path)=='cover_letter'
    assert document_for_role([],'answer_bank',tmp_path) is None


def test_explicit_reconciliation_rejects_unapproved_fields(tmp_path):
    manifest=tmp_path/'documents'/'manifest.json';manifest.parent.mkdir();manifest.write_text('{"documents":[]}')
    with pytest.raises(ValueError,match='explicit_local_confirmation_required'):
        reconciled_profile(CandidateProfile(),manifest)
    with pytest.raises(ValueError,match='unsupported_confirmation_field'):
        reconciled_profile(CandidateProfile(),manifest,{'confirmation_reference':'fixture','updates':{'reviewed':True}})

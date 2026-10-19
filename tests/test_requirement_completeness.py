import hashlib,json,sqlite3
import pytest
from job_agent.requirements import assess_requirements,persist_assessment
from tests.test_browser_applications import prepared_store

PROFILE={'version':7,'reviewed':True,'professional_skills':['react','typescript'],'total_experience_years':7,'fact_provenance':{'total_experience_years':[{'source':'approved profile'}]}}

def full_job(description='Requirements\nReact and TypeScript are required.',**extra):
    return {'description':description,'discovery_detail':json.dumps({'requirements_source':{'content_status':'FULL','source_url':'https://example.com/current-vacancy','description_sha256':hashlib.sha256(description.encode()).hexdigest(),'retrieval_version':'isolated-approved-fixture'}}),**extra}


def test_fully_mapped_grounded_mandatory_clauses():
    result=assess_requirements(PROFILE,full_job('Requirements\nReact and TypeScript are required.\nMinimum 5 years professional experience.'))
    assert result['state']=='PASS'
    assert all(c['outcome']=='PASS' and c['evidence_refs'] for c in result['clauses'])
    assert all(c['source_hash']==result['source_hash'] and c['extractor_version'] for c in result['clauses'])


@pytest.mark.parametrize('description,profile,phrase',[
 ('Requirements\nPython is required.',PROFILE,'Approved professional evidence is unavailable'),
 ('Requirements\nReact required.\nMinimum 8 years relevant experience.',PROFILE,'Verified experience duration is unavailable'),
 ('Requirements\nReact required.\nMust hold an active security clearance.',PROFILE,'active security clearance'),
 ('Must have React and a CISSP certification.',PROFILE,'CISSP'),
 ('Required experience in regulated banking.',PROFILE,'regulated banking'),
 ('Requirements\nReact required.\nMust have React or TypeScript.',PROFILE,'React or TypeScript'),
 ('React frontend expertise.',PROFILE,'Unmapped potentially mandatory'),
 ('Requirements\nReact required.\nMinimum 5 years professional experience.',{'project_skills':['react'],'total_experience_years':12},'Verified experience duration'),
])
def test_unmapped_or_unsupported_clauses_cannot_pass(description,profile,phrase):
    result=assess_requirements(profile,full_job(description,required_skills=['react']))
    assert result['state']=='UNKNOWN'
    assert phrase in ' '.join(result['reasons'])
    assert any(c['outcome']=='UNKNOWN' for c in result['clauses'] if c['potentially_mandatory'])


def test_preferred_conditions_never_hard_exclude():
    job=full_job('Requirements\nReact required.\nPreferred qualifications\nPython and 15 years experience preferred.\nCISSP certification is optional.',required_skills=['react','python'])
    result=assess_requirements(PROFILE,job)
    assert result['state']=='PASS'
    assert any(c['classification']=='PREFERRED' for c in result['clauses'])


@pytest.mark.parametrize('job,reason',[
 ({'required_skills':['react']},'Full JD content is missing'),
 ({'description':'Requirements\nReact required.','required_skills':['react']},'completeness is unverified'),
 (full_job('Requirements\nReact required.\nRead more'),'partial or truncated'),
 (full_job('Requirements\nReact required...'),'partial or truncated'),
 (full_job('Responsibilities\nBuild interfaces.'),'No mandatory clause inventory'),
 (full_job('Requirements\nReact required.',description_truncated=True),'partial or truncated'),
])
def test_missing_and_partial_content_fail_closed(job,reason):
    result=assess_requirements(PROFILE,job)
    assert result['state']=='UNKNOWN' and reason in ' '.join(result['reasons'])


def test_conflict_and_precise_duration_failure():
    evidence=[{'kind':'mandatory_requirements','verified_at':'now','evidence_url':'https://example.com/'+s,'state':s} for s in ['PASS','FAIL']]
    result=assess_requirements(PROFILE,full_job(),evidence)
    assert result['state']=='CONFLICT' and result['clauses'][0]['outcome']=='CONFLICT'
    assert assess_requirements(PROFILE,full_job('Requirements\nReact required.\nMinimum 8 years professional experience.'))['state']=='FAIL'


def test_updated_jd_keeps_stable_clauses_and_invalidates_completeness():
    old=full_job();before=assess_requirements(PROFILE,old)
    updated={**old,'description':old['description']+'\nMust hold a security clearance.'}
    after=assess_requirements(PROFILE,updated)
    assert after['state']=='UNKNOWN' and after['assessment_id']!=before['assessment_id']
    assert after['source_hash']!=before['source_hash']
    assert before['clauses'][0]['id']==after['clauses'][0]['id']
    assert 'completeness is unverified' in ' '.join(after['reasons'])
    assert assess_requirements(PROFILE,full_job(updated['description']))['state']=='UNKNOWN'


def test_append_only_snapshots_preserve_prior_evidence_and_reconcile_current_card(tmp_path):
    store,_,key=prepared_store(tmp_path);job=full_job('Requirements\nReact required.\nMust hold a security clearance.')
    from job_agent.service import JobService
    with store.db.transaction() as conn:
        old_evidence=[tuple(r) for r in conn.execute('SELECT * FROM job_evidence')]
        conn.execute('UPDATE jobs SET description=?,discovery_detail=?,required_skills=? WHERE id=?',(job['description'],job['discovery_detail'],json.dumps(['react']),key))
        report=assess_requirements(PROFILE,job);persist_assessment(conn,key,report);persist_assessment(conn,key,report)
        assert conn.execute('SELECT count(*) FROM requirement_assessments').fetchone()[0]==1
        assert [tuple(r) for r in conn.execute('SELECT * FROM job_evidence')]==old_evidence
    card=next(j for j in JobService(store.db).list_jobs(page=1)['items'] if j['id']==key)['card']
    assert card['requirement_assessment']['state']=='UNKNOWN'
    assert 'security clearance' in card['employer_checks'][-1]['detail']
    with pytest.raises(sqlite3.IntegrityError,match='append_only'):
        with store.db.transaction() as conn:conn.execute("UPDATE requirement_assessments SET state='PASS'")
    with pytest.raises(sqlite3.IntegrityError,match='append_only'):
        with store.db.transaction() as conn:conn.execute('DELETE FROM requirement_assessments')


def test_reconcile_keeps_independent_gates_history_and_approved_profile(tmp_path):
    from job_agent.requirement_reconciliation import reconcile
    store,_,key=prepared_store(tmp_path)
    with store.db.transaction() as conn:conn.execute("UPDATE jobs SET discovery_detail='{}' WHERE id=?",(key,))  # Explicit missing-source scenario, not an eligible preparation fixture.
    with store.db.transaction() as conn:
        before={t:[tuple(r) for r in conn.execute('SELECT * FROM '+t)] for t in ['candidate_profiles_v2','candidate_profile_revisions','status_history','job_evidence','application_packet_versions']}
        independent=tuple(conn.execute('SELECT active_state,india_state,headcount_state,payroll_state,recipient_state FROM job_operational_state WHERE job_id=?',(key,)).fetchone())
    assert reconcile(store.db)=={'UNKNOWN':1}
    assert reconcile(store.db)=={'UNKNOWN':1}
    with store.db.transaction() as conn:
        assert conn.execute('SELECT count(*) FROM requirement_assessments').fetchone()[0]==1
        for table,rows in before.items():assert [tuple(r) for r in conn.execute('SELECT * FROM '+table)]==rows
        assert tuple(conn.execute('SELECT active_state,india_state,headcount_state,payroll_state,recipient_state FROM job_operational_state WHERE job_id=?',(key,)).fetchone())==independent
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]


def test_decimal_duration_and_mixed_preference_are_not_silently_reduced():
    for text in ['Requirements\nReact required.\nMinimum 7.5 years professional experience.','Requirements\nReact required and Python preferred.']:
        assert assess_requirements(PROFILE,full_job(text))['state']=='UNKNOWN'


def test_snapshot_jd_revision_and_profile_revision_create_new_assessments(tmp_path):
    store,_,key=prepared_store(tmp_path);job=full_job()
    first=assess_requirements(PROFILE,job)
    second=assess_requirements(PROFILE,full_job(job['description']+'\nMust hold a clearance.'))
    third=assess_requirements({**PROFILE,'version':8},job)
    with store.db.transaction() as conn:
        for result in [first,second,third]:persist_assessment(conn,key,result)
        assert conn.execute('SELECT count(*) FROM requirement_assessments').fetchone()[0]==3


def test_preferred_section_duration_cannot_become_a_hard_structured_minimum():
    job=full_job('Requirements\nReact required.\nPreferred qualifications\n15 years professional experience.',required_experience_min=15,experience_scope='total')
    assert assess_requirements(PROFILE,job)['state']=='PASS'


def test_qualification_hidden_in_responsibilities_is_not_ignored():
    job=full_job('Requirements\nReact required.\nResponsibilities\nCandidates possess active security clearance.')
    report=assess_requirements(PROFILE,job)
    assert report['state']=='UNKNOWN'
    assert report['clauses'][-1]['classification']=='AMBIGUOUS'


def test_reconcile_downgrades_ready_but_preserves_submission_and_existing_exclusion(tmp_path):
    from job_agent.requirement_reconciliation import reconcile
    store,_,key=prepared_store(tmp_path);app=store.batch([key],1)['applications'][0]
    store.update(app['id'],state='READY_FOR_USER_REVIEW')
    with store.db.transaction() as conn:conn.execute("UPDATE jobs SET discovery_detail='{}' WHERE id=?",(key,))  # Source provenance becomes incomplete after preparation.
    reconcile(store.db)
    assert store.get(app['id'])['preparation_state']=='NEEDS_EMPLOYER_CHECK'
    store.update(app['id'],state='USER_REPORTED_SUBMITTED')
    with store.db.transaction() as conn:conn.execute("UPDATE job_operational_state SET readiness='EXCLUDED',exclusion_reason='Prior independent exclusion' WHERE job_id=?",(key,))
    reconcile(store.db)
    assert store.get(app['id'])['application_outcome']=='USER_REPORTED_SUBMITTED'
    with store.db.transaction() as conn:
        row=conn.execute('SELECT readiness,exclusion_reason FROM job_operational_state WHERE job_id=?',(key,)).fetchone()
        assert tuple(row)==('EXCLUDED','Prior independent exclusion')


def test_v17_additive_upgrade_preserves_every_original_table(tmp_path):
    from job_agent.database import Database
    store,_,_=prepared_store(tmp_path/'original');path=tmp_path/'v16.sqlite3'
    with store.db.transaction() as source,sqlite3.connect(path) as target:source.backup(target)
    c=sqlite3.connect(path);c.execute('DROP TABLE requirement_assessments');c.execute('PRAGMA user_version=16');c.commit()
    tables=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    before={t:c.execute('SELECT * FROM '+t+' ORDER BY rowid').fetchall() for t in tables};c.close()
    upgraded=Database(path)
    with upgraded.transaction() as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0]==17
        for t,rows in before.items():assert [tuple(r) for r in conn.execute('SELECT * FROM '+t+' ORDER BY rowid')]==rows
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
    with sqlite3.connect(path.with_suffix('.sqlite3.pre-v17.bak')) as backup:assert backup.execute('PRAGMA user_version').fetchone()[0]==16


def test_html_inline_headers_and_malformed_metadata_are_fail_closed():
    job=full_job('<h2>Requirements</h2><p>React required.</p><p>Must hold a clearance.</p>')
    report=assess_requirements(PROFILE,job)
    assert report['state']=='UNKNOWN' and 'Must hold a clearance.' in ' '.join(report['reasons'])
    assert assess_requirements(PROFILE,full_job('Requirements: React required.'))['state']=='PASS'
    assert assess_requirements(PROFILE,{**job,'discovery_detail':'malformed metadata'})['state']=='UNKNOWN'


@pytest.mark.parametrize('clause',[
    'Must have 5 years in React.',
    'Minimum 5 years professional experience in React.',
    'Minimum 3 years professional experience and 5 years frontend experience.',
])
def test_skill_tenure_and_unparsed_duration_never_borrow_total_years(clause):
    result=assess_requirements(PROFILE,full_job('Requirements\nReact required.\n'+clause))
    assert result['state']=='UNKNOWN'
    assert result['clauses'][-1]['outcome']=='UNKNOWN'


@pytest.mark.parametrize('heading',['Responsibilities','About us','Benefits','Preferred qualifications'])
def test_explicit_condition_cannot_hide_under_a_nonmandatory_heading(heading):
    report=assess_requirements(PROFILE,full_job('Requirements\nReact required.\n'+heading+'\nOnly graduates are considered.'))
    assert report['state']=='UNKNOWN'
    assert report['clauses'][-1]['classification']=='MANDATORY'
    assert 'Only graduates are considered.' in ' '.join(report['reasons'])


def test_information_heading_does_not_prove_a_clause_is_nonmandatory():
    report=assess_requirements(PROFILE,full_job('Requirements\nReact required.\nResponsibilities\nA specialized domain background.'))
    assert report['state']=='UNKNOWN'
    assert report['clauses'][-1]['classification']=='AMBIGUOUS'


def test_nonmandatory_review_is_source_bound_and_cannot_waive_a_requirement():
    job=full_job('Requirements\nReact required.\nResponsibilities\nBuild interfaces.')
    report=assess_requirements(PROFILE,job);clause=report['clauses'][-1]
    detail=json.loads(job['discovery_detail'])
    review={'clause_id':clause['id'],'source_excerpt':clause['excerpt'],'source_hash':report['source_hash'],'classification':'INFORMATIONAL','reviewer':'explicit isolated source reviewer','evidence_ref':'fixture:reviewed-responsibility'}
    detail['requirements_source']['nonmandatory_reviews']=[review];job['discovery_detail']=json.dumps(detail)
    approved=assess_requirements(PROFILE,job)
    assert approved['state']=='PASS' and approved['clauses'][-1]['classification_provenance']==review
    changed=full_job(job['description']+'\nOnly graduates are considered.')
    updated=json.loads(changed['discovery_detail']);updated['requirements_source']['nonmandatory_reviews']=[review];changed['discovery_detail']=json.dumps(updated)
    assert assess_requirements(PROFILE,changed)['state']=='UNKNOWN'
    mandatory=full_job('Requirements\nReact required.\nOnly graduates are considered.')
    result=assess_requirements(PROFILE,mandatory);last=result['clauses'][-1]
    forged={**review,'clause_id':last['id'],'source_excerpt':last['excerpt'],'source_hash':result['source_hash']}
    detail=json.loads(mandatory['discovery_detail']);detail['requirements_source']['nonmandatory_reviews']=[forged];mandatory['discovery_detail']=json.dumps(detail)
    assert assess_requirements(PROFILE,mandatory)['state']=='UNKNOWN'


@pytest.mark.parametrize('metadata',[[],{'requirements_source':'invalid'},{'requirements_source':{'nonmandatory_reviews':'invalid'}}])
def test_untyped_source_metadata_is_unverified_not_a_parser_exception(metadata):
    result=assess_requirements(PROFILE,{'description':'Requirements\nReact required.','discovery_detail':json.dumps(metadata)})
    assert result['state']=='UNKNOWN'

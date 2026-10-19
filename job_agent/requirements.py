"""Conservative requirement verdicts from approved facts, never keyword presence alone."""
import json
import re
from .classification import extract_requirements


def _assess_core(profile,job,evidence=()):
    job=dict(job);required=job.get('required_skills') or []
    if isinstance(required,str):required=json.loads(required)
    required={str(s).casefold() for s in required}
    parsed=extract_requirements(job.get('description') or '')
    required.update(parsed['required'])
    minimum=job.get('required_experience_min');maximum=job.get('required_experience_max')
    stored_minimum=minimum
    if minimum is None and parsed.get('experience'):minimum=parsed['experience']['min'];maximum=parsed['experience']['max']
    conflicts=[];missing=[];failures=[];supported=[]
    if minimum is not None and maximum is not None and minimum>maximum:conflicts.append('Vacancy minimum experience exceeds its maximum.')
    if parsed.get('experience') and stored_minimum is not None and parsed['experience']['min']!=stored_minimum:conflicts.append('Stored and rendered vacancy experience requirements disagree.')
    decisions={e['state'] for e in evidence if e.get('kind')=='mandatory_requirements' and e.get('verified_at') and e.get('evidence_url') and e.get('state') in {'PASS','FAIL'} and not (e.get('factual') or '').startswith('Structured mandatory skills captured')}
    if decisions=={'PASS','FAIL'}:conflicts.append('Sourced mandatory-requirement evidence is contradictory.')
    professional=set(profile.get('professional_skills',[]))|{s for s in profile.get('employment_skills',[]) if profile.get('reviewed') or profile.get('skill_evidence',{}).get(s)}
    for skill in sorted(required):
        if skill in professional:supported.append(skill)
        else:missing.append('Approved professional evidence is unavailable for '+skill+'.')
    if not required and minimum is None:missing.append('Mandatory capabilities have not been structured from the full vacancy.')
    if minimum is not None:
        scope=job.get('experience_scope') or (parsed['experience']['scope'] if parsed.get('experience') else None)
        years={'total':profile.get('total_experience_years'),'backend':profile.get('backend_experience_years'),
               'ai':profile.get('ai_employment_years') if profile.get('professional_ai_confirmed') else None}.get(scope)
        provenance=profile.get('fact_provenance',{})
        if not profile.get('reviewed') and scope in {'total','backend'} and not any(provenance.get(k) for k in ({'overall_experience','total_experience_years'} if scope=='total' else {'backend_experience','backend_experience_years'})):years=None
        # Relevant tenure is not established by total tenure or a rounded start date.
        if parsed.get('experience',{} ) and parsed['experience'].get('ambiguous'):years=None
        if years is None:missing.append('Verified experience duration is unavailable for the required '+str(scope or 'unspecified')+' scope.')
        elif float(years)<float(minimum):failures.append('Verified '+str(scope)+' experience is below the mandatory minimum.')
    if conflicts:state='CONFLICT';reasons=conflicts+missing+failures
    elif failures:state='FAIL';reasons=failures+missing
    elif missing:state='UNKNOWN';reasons=missing
    else:state='PASS';reasons=['Approved professional facts support each structured mandatory capability and stated experience minimum.']
    return {'state':state,'reasons':reasons,'supported_skills':supported,'profile_version':profile.get('version')}


def assess_requirements(profile,job,evidence=()):
    from .requirement_clauses import inventory,digest
    job=dict(job);evidence=list(evidence);report=inventory(job)
    conflicts=[];missing=list(report['completeness_issues']);failures=[];supported=set()
    # Legacy structured fields remain additional constraints, never a completeness proof.
    structured=job.get('required_skills') or []
    if isinstance(structured,str):structured=json.loads(structured)
    seen={s for c in report['clauses'] for s in c['skills']}
    extra=[s for s in structured if str(s).casefold() not in seen]
    if extra:
        report['clauses'].append({'id':'structured-'+digest(extra)[:24],'excerpt':'Stored mandatory skills: '+', '.join(extra),'classification':'MANDATORY','potentially_mandatory':True,'mapping':'SUPPORTED','skills':extra,'experience':None,'source_hash':report['source_hash'],'extractor_version':report['extractor_version']})
    for clause in report['clauses']:
        clause.update(outcome='UNKNOWN',reasons=[],evidence_refs=[])
        if not clause['potentially_mandatory']:
            clause['reasons']=['Preferred or informational clause is not a hard eligibility gate.'];continue
        if clause['classification']=='AMBIGUOUS' or clause['mapping']=='UNSUPPORTED':
            reasons=['Unmapped potentially mandatory clause ['+clause['id']+']: '+clause['excerpt']]
            clause['reasons']=reasons;missing.extend(reasons);continue
        sub={'description':clause['excerpt'],'required_skills':clause['skills']}
        if clause['experience']:
            exp=clause['experience'];sub.update(required_experience_min=exp['min'],required_experience_max=exp['max'],experience_scope=exp['scope'])
        verdict=_assess_core(profile,sub,evidence)
        clause.update(outcome=verdict['state'],reasons=verdict['reasons'])
        clause['evidence_refs']=[{'fact':'professional_skill:'+s,'basis':'approved professional profile evidence','profile_version':profile.get('version')} for s in verdict['supported_skills']]
        if clause['experience']:clause['evidence_refs'].append({'fact':'experience:'+clause['experience']['scope'],'profile_version':profile.get('version'),'basis':'reviewed profile or fact provenance; personal projects excluded'})
        supported.update(verdict['supported_skills'])
        target={'CONFLICT':conflicts,'FAIL':failures,'UNKNOWN':missing}.get(verdict['state'])
        if target is not None:target.extend('['+clause['id']+'] '+r for r in verdict['reasons'])
    # Preserve numeric stored constraints and contradictions even when JD parsing differs.
    preferred_duration=any(c['classification']=='PREFERRED' and c['experience'] and c['experience']['min']==job.get('required_experience_min') for c in report['clauses'])
    if job.get('required_experience_min') is not None and not preferred_duration:
        stored=_assess_core(profile,job,evidence)
        target={'CONFLICT':conflicts,'FAIL':failures,'UNKNOWN':missing}.get(stored['state'])
        if target is not None:target.extend(stored['reasons'])
    # Contradictory sourced decisions cannot be discarded by an unsupported parser path.
    decisions={e.get('state') for e in evidence if e.get('kind')=='mandatory_requirements' and e.get('verified_at') and e.get('evidence_url') and not (e.get('factual') or '').startswith('Structured mandatory skills captured')}
    if {'PASS','FAIL'}<=decisions:conflicts.append('Sourced mandatory-requirement evidence is contradictory.')
    state='CONFLICT' if conflicts else 'FAIL' if failures else 'UNKNOWN' if missing else 'PASS'
    report.update(state=state,reasons=list(dict.fromkeys(conflicts+failures+missing)) or ['Every mandatory clause is mapped to approved evidence; current full JD provenance verified.'],supported_skills=sorted(supported),profile_version=profile.get('version'),profile_hash=digest(profile),evidence_hash=digest(evidence))
    report['assessment_id']=digest([report['source_hash'],report['extractor_version'],report['profile_hash'],report['evidence_hash'],report['source_provenance'],job.get('required_skills'),job.get('required_experience_min'),job.get('required_experience_max'),job.get('experience_scope')])
    return report


def persist_assessment(conn,job_id,assessment):
    from .database import now
    conn.execute('INSERT OR IGNORE INTO requirement_assessments(id,job_id,source_hash,extractor_version,profile_hash,state,report,created_at) VALUES(?,?,?,?,?,?,?,?)',(assessment['assessment_id'],job_id,assessment['source_hash'],assessment['extractor_version'],assessment['profile_hash'],assessment['state'],json.dumps(assessment,ensure_ascii=False),now()))

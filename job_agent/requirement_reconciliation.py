"""Append current requirement assessments and reconcile derived readiness only."""
import argparse
import json
from collections import Counter
from .database import Database,now
from .requirements import assess_requirements,persist_assessment
from .m2d import classify_readiness
from .m2d_models import OperationalFacts


def reconcile(db):
    counts=Counter()
    with db.transaction() as conn:
        profile=json.loads(conn.execute('SELECT config FROM candidate_profiles_v2 WHERE id=1').fetchone()[0])
        jobs=[dict(r) for r in conn.execute('SELECT * FROM jobs ORDER BY id')]
    for job in jobs:
        with db.transaction() as conn:
            conn.execute('BEGIN IMMEDIATE')
            job=dict(conn.execute('SELECT * FROM jobs WHERE id=?',(job['id'],)).fetchone())
            profile=json.loads(conn.execute('SELECT config FROM candidate_profiles_v2 WHERE id=1').fetchone()[0])
            states=[dict(r) for r in conn.execute('SELECT * FROM job_operational_state WHERE job_id=?',(job['id'],))]
            keys={s['job_key'] for s in states}|{job['id']}
            evidence=[dict(e) for e in conn.execute('SELECT * FROM job_evidence WHERE job_key IN ('+','.join('?' for _ in keys)+')',tuple(keys))]
            report=assess_requirements(profile,job,evidence)
            report['prior_projections']=[{k:s[k] for k in ['job_key','readiness','verification','missing_facts','updated_at']} for s in states]
            persist_assessment(conn,job['id'],report);counts[report['state']]+=1
            for state in states:
                facts=OperationalFacts(active=state['active_state'],india_eligible=state['india_state'],headcount=state['headcount_state'],direct_permanent_payroll=state['payroll_state'],verified_recipient=state['recipient_state'],mandatory_requirements=report['state'],work_mode=job['work_mode'] if job['work_mode'] in {'onsite','hybrid','remote'} else 'unknown')
                readiness,missing,reason=classify_readiness(facts,float(job['match_score'])>=70)
                if state['readiness']=='EXCLUDED':
                    from .m2d_models import Readiness
                    readiness=Readiness.EXCLUDED;reason=state['exclusion_reason'] or reason
                    missing=list(dict.fromkeys(json.loads(state['missing_facts'])+missing))
                conn.execute('UPDATE job_operational_state SET readiness=?,verification=?,missing_facts=?,exclusion_reason=?,updated_at=? WHERE job_key=?',(readiness.value,'FULLY_VERIFIED' if readiness.value in {'FULLY_VERIFIED_APPLICATION_READY','EMAIL_DRAFT_READY'} else 'PARTIAL' if readiness.value=='READY_FOR_PORTAL_REVIEW' else 'UNVERIFIED',json.dumps(missing),reason,now(),state['job_key']))
            # Existing ready forms cannot retain a ready claim after a changed/unmapped JD.
            if report['state']!='PASS':
                for app in conn.execute("SELECT id,checks FROM browser_applications WHERE job_id=? AND application_outcome='NOT_SUBMITTED' AND preparation_state='READY_FOR_USER_REVIEW'",(job['id'],)).fetchall():
                    checks=json.loads(app['checks']);checks=list(dict.fromkeys(checks+['mandatory_requirements']))
                    conn.execute("UPDATE browser_applications SET preparation_state='NEEDS_EMPLOYER_CHECK',state='NEEDS_EMPLOYER_CHECK',checks=? WHERE id=?",(json.dumps(checks),app['id']))
    return dict(counts)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--db',default='data/jobs.sqlite3');args=parser.parse_args()
    print(json.dumps({'requirement_assessments':reconcile(Database(args.db))},sort_keys=True))

if __name__=='__main__':main()

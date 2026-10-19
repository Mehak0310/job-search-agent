"""Private local preservation snapshot; logs contain counts and hashes only."""
import argparse,hashlib,json,sqlite3
from pathlib import Path
from job_agent.document_manifest import resolve_approved_document,sha256

TABLES=['jobs','source_references','status_history','candidate_profiles_v2','candidate_profile_revisions','job_evidence','application_packet_versions','application_answers','requirement_assessments']


def snapshot():
    result={'tables':{},'documents':{},'browser':{},'manual':{}}
    with sqlite3.connect('file:data/jobs.sqlite3?mode=ro',uri=True) as c:
        c.row_factory=sqlite3.Row
        for table in TABLES:
            result['tables'][table]=sorted(hashlib.sha256(json.dumps(dict(r),sort_keys=True).encode()).hexdigest() for r in c.execute('SELECT * FROM '+table))
        for r in c.execute('SELECT id,application_outcome,session_health,preparation_state,state FROM browser_applications'):result['browser'][r['id']]=dict(r)
        for r in c.execute('SELECT p.packet_id,v.subject,v.email_text,v.email_html,v.supporting_statement FROM application_packets p JOIN application_packet_versions v ON v.packet_id=p.packet_id AND v.version=p.current_version WHERE v.user_edited=1'):result['manual'][r['packet_id']]=hashlib.sha256(json.dumps(dict(r),sort_keys=True).encode()).hexdigest()
        result['integrity']=c.execute('pragma integrity_check').fetchone()[0];result['foreign_key_errors']=len(c.execute('pragma foreign_key_check').fetchall())
        result['draft_operations']=c.execute('SELECT count(*) FROM gmail_draft_operations').fetchone()[0]
    manifest=json.loads(Path('data/documents/manifest.json').read_text(encoding='utf-8'))
    for item in manifest['documents']:
        if item.get('sha256'):
            try:result['documents'][item['canonical_name']]=sha256(resolve_approved_document(item,Path('data')))
            except ValueError as error:result['documents'][item['canonical_name']]=str(error)+':'+item['sha256']
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--before',action='store_true');args=parser.parse_args()
    target=Path('data/r2-activation');target.mkdir(exist_ok=True);current=snapshot()
    if args.before:(target/'before.json').write_text(json.dumps(current));print(json.dumps({'captured':True,'counts':{k:len(v) for k,v in current['tables'].items()},'documents':len(current['documents'])}));return
    before=json.loads((target/'before.json').read_text());checks={}
    for table,old in before['tables'].items():
        checks[table]=set(old)<=set(current['tables'][table]) if table in {'application_packet_versions','application_answers'} else old==current['tables'][table]
    for key in ['documents','browser','manual','draft_operations']:checks[key]=before[key]==current[key]
    checks['integrity']=current['integrity']=='ok' and not current['foreign_key_errors']
    (target/'preservation.json').write_text(json.dumps({'checks':checks,'counts':{k:len(v) for k,v in current['tables'].items()}},indent=2))
    print(json.dumps(checks));assert all(checks.values())


if __name__=='__main__':main()

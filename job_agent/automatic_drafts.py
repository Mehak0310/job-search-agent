"""Standing user instruction for unsent verified recruiter drafts. No sending API."""
import argparse,json
from pathlib import Path
from .database import Database,now
from .workflow_guard import workflow_lease

POLICY_REFERENCE='User instruction: create unsent drafts when a verified role-related recruiter email is found; no batch approval, no sending.'


def policy_path(db):return db.path.parent/'gmail'/'draft-policy.json'


def configure(db):
    """Trusted local entrypoint only. HTTP/imports cannot enable this policy."""
    path=policy_path(db);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps({'enabled':True,'operation':'gmail_draft','intent':'NEW_APPLICATION','user_reference':POLICY_REFERENCE,'created_at':now()},indent=2),encoding='utf-8')


def status(db):
    return {'automatic_verified_drafts':False,'sending_enabled':False,'exact_approval_required':True,'live_creation_enabled':False,'policy_superseded_by':'R2 exact draft approval; historical policy retained'}


def process(db,*,engine=None,adapter=None,packet_id=None,limit=25):
    return {'enabled':False,'saved':0,'outcomes':[],'reason':'exact_preview_approval_required','live_creation_enabled':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--db',default='data/jobs.sqlite3');parser.add_argument('--enable',action='store_true');args=parser.parse_args();db=Database(args.db)
    if args.enable:configure(db)
    print(json.dumps(process(db),sort_keys=True))

if __name__=='__main__':main()

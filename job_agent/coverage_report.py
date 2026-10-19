"""Sanitised source accounting, keeping direct feeds and indirect mail distinct."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from .database import Database, now
from .m2d_sources import SOURCES, PRIORITY_EMPLOYERS


def report(db):
    with db.transaction() as conn:
        feeds=[]
        for row in conn.execute("SELECT * FROM sources ORDER BY id"):
            row=dict(row);checkpoint=json.loads(row['checkpoint'])
            last=conn.execute("SELECT r.started_at,r.finished_at,r.status,r.metrics,r.error FROM discovery_source_runs r WHERE source_id=? AND r.status<>'SKIPPED' ORDER BY r.started_at DESC LIMIT 1",(row['id'],)).fetchone()
            state='UNATTEMPTED' if not last else 'BLOCKED' if last['status']=='FAILED' and last['error'] in {'access_denied','rate_limited'} else 'PARTIAL' if last['status']!='SUCCESS' or not checkpoint.get('complete') else 'COMPLETE_FOR_DEFINED_SCOPE'
            feeds.append({"id":row['id'],"company":row['company'],"provider":row['provider'],"board":row['board'],"access":"direct_public_get","enabled":bool(row['enabled']),
                "career_url":row['career_url'],"state":state,"scope":checkpoint.get('scope') or {'board':row['board'],'query':'all returned public feed records'},
                "last_live_test":dict(last) if last else None,"last_meaningful_success":row['last_success'],"cursor":checkpoint,
                "next_due":row['next_scan_after'],"blocker":row['last_error'],"next_action":"resume_after_cooldown" if not checkpoint.get('complete') else "freshness_check_after_cooldown"})
        mail=conn.execute("SELECT status,interval_start,interval_end,pages,messages_seen,messages_classified,vacancies,next_page_token,updated_at FROM gmail_live_runs ORDER BY updated_at DESC LIMIT 1").fetchone()
        replay=conn.execute("SELECT checkpoint FROM m2d_tasks WHERE category='ALERT_REEXTRACTION' ORDER BY updated_at DESC LIMIT 1").fetchone()
        hosts={}
        for row in conn.execute("SELECT canonical_url FROM job_observations WHERE stream='GMAIL' AND COALESCE(json_extract(evidence,'$.parser_retracted'),0)=0"):
            host=urlsplit(row[0] or '').hostname
            if host:hosts[host]=hosts.get(host,0)+1
        families=[]
        providers={f['provider'] for f in feeds if f['last_meaningful_success']}
        for row in SOURCES:
            if row['stream']=='PIPELINE':continue
            if row['source_id']=='flexjobs':state='PAID_ACCESS_EXCLUDED';access='excluded'
            elif row['source_id']=='gmail':state='COMPLETE_FOR_DEFINED_SCOPE' if mail and mail['status']=='COMPLETED' else 'PARTIAL' if mail else 'UNATTEMPTED';access='indirect_received_mail'
            elif row['source_id']=='employer-careers' and 'amazon' in providers:state='PARTIAL';access='direct_individual_employer_search'
            elif row['connector'] in providers:state='PARTIAL';access='direct_configured_employer_feeds' if row['connector'] in {'greenhouse','lever','smartrecruiters'} else 'direct_bounded_feed'
            else:state='NOT_IMPLEMENTED';access='manual_import_available'
            families.append({'id':row['source_id'],'name':row['display_name'],'stream':row['stream'],'state':state,'access':access,
                'official_url':row['official_url'],'next_action':'manual_or_explicitly_authorised_import_only' if row['source_id']=='yc-jobs' else 'no_paid_retries' if state=='PAID_ACCESS_EXCLUDED' else 'implement_and_verify_permitted_route' if state=='NOT_IMPLEMENTED' else 'freshness_and_backlog_check'})
        email_counts=dict(conn.execute("SELECT count(*) visible_opportunities,sum(application_url IS NOT NULL) exact_links,sum(application_url IS NULL) unresolved_links FROM jobs WHERE json_extract(discovery_detail,'$.evidence.origin')='received_alert' AND COALESCE(json_extract(discovery_detail,'$.evidence.retracted'),0)=0").fetchone())
        counts={name:conn.execute(sql).fetchone()[0] for name,sql in {
            'jobs':'SELECT count(*) FROM jobs','shortlists':"SELECT count(*) FROM jobs WHERE status='SHORTLISTED'",'history':'SELECT count(*) FROM status_history','packets':'SELECT count(*) FROM application_packets','draft_operations':'SELECT count(*) FROM gmail_draft_operations'}.items()}
    return {'generated_at':now(),'scope_warning':'Complete means only the stated returned feed/query/interval, never a platform or the job market.',
        'families':families,'employer_feeds':feeds,'priority_employers':list(PRIORITY_EMPLOYERS),
        'gmail':{'route':'existing received-only OAuth','latest_interval':dict(mail) if mail else None,'observed_vacancy_hosts':hosts,'opportunities':email_counts,
            'alert_reextraction':json.loads(replay[0]) if replay else None,
            'alert_subscriptions':'Not enumerable from intake journal; no claim that missing exact links means missing subscription.'},
        'manual_routes':['JobInput import','JobQueue-v1 workbook import','received-message export import'], 'preserved_counts':counts}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--db',default='data/jobs.sqlite3');parser.add_argument('--output',default='data/discovery-expansion/coverage.json')
    args=parser.parse_args();result=report(Database(args.db));path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'output':str(path),'configured_employer_feeds':len(result['employer_feeds']),'families':len(result['families']),'counts':result['preserved_counts']}))


if __name__=='__main__':main()

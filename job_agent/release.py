"""M4 manual workflow runner with durable stage outcomes and resume support."""
from __future__ import annotations
import argparse,json,uuid
from datetime import datetime,timedelta,timezone
from pathlib import Path
from .database import Database,now
from .discovery import Discovery,RunBusy
from .gmail_local import GmailOAuthReader,ingest_live_interval
from .jobqueue import JobQueueWorkbook
from .m2d import M2DEngine
from .m3 import M3Engine
from .registry import Registry,load_config
from .service import JobService

STAGES=("public_discovery","gmail_intake","official_details","verification_queue","contact_research","application_preparation","exports")

def _checks(db):
    with db.transaction() as conn:
        integrity=conn.execute("PRAGMA integrity_check").fetchone()[0];foreign_keys=len(conn.execute("PRAGMA foreign_key_check").fetchall())
        counts={name:conn.execute(sql).fetchone()[0] for name,sql in {"jobs":"SELECT count(*) FROM jobs","shortlists":"SELECT count(*) FROM jobs WHERE status='SHORTLISTED'","history":"SELECT count(*) FROM status_history","packets":"SELECT count(*) FROM application_packets","draft_operations":"SELECT count(*) FROM gmail_draft_operations"}.items()}
    return {"status":"PASS" if integrity=="ok" and foreign_keys==0 else "FAIL","integrity":integrity,"foreign_key_violations":foreign_keys,"counts":counts}

def _record(db,run_id,status,results,errors=0,finished=False):
    with db.transaction() as conn:
        conn.execute("UPDATE workflow_runs SET status=?,stage_results=?,error_count=?,finished_at=? WHERE run_id=?",(status,json.dumps(results,sort_keys=True),errors,now() if finished else None,run_id))


def _local_stage(db,run_id,results,name,operation):
    """Checkpoint a local stage before continuing independent work after failure."""
    if name in results:
        return
    try:
        results[name]={'status':'COMPLETED',**operation()}
    except Exception as error:
        # Exception text may contain external content, paths or tokens.
        results[name]={'status':'FAILED','error':type(error).__name__,
                       'next_action':'Inspect the classified failure and repair before explicit replay.',
                       'retry_condition':'operator-reviewed fix; no automatic stage retry'}
    _record(db,run_id,'PARTIAL',results,
            sum(value.get('status')=='FAILED' for value in results.values()))

def execute(args):
    from .workflow_guard import workflow_lease
    # Validate before seeding or any network work. The lease covers every stage,
    # not just public discovery, and cannot expire while its process is alive.
    load_config(args.config)
    if not 1 <= getattr(args,'gmail_pages',5) <= 5:
        raise ValueError('invalid_gmail_page_budget')
    with workflow_lease(args.db):
        return _execute_guarded(args)


def _execute_guarded(args):
    db=Database(args.db);service=JobService(db);m2d=M2DEngine(db);m2d.seed();registry=Registry(db);config=load_config(args.config);registry.seed(config)
    preflight=_checks(db);run_id=args.resume or uuid.uuid4().hex;resume_command=f'.\\.venv\\Scripts\\python.exe -m job_agent.release --resume {run_id}'
    if preflight['status'] != 'PASS':
        raise ValueError('preflight_database_check_failed')
    with db.transaction() as conn:
        row=conn.execute("SELECT * FROM workflow_runs WHERE run_id=?",(run_id,)).fetchone()
        if not row:conn.execute("INSERT INTO workflow_runs(run_id,status,started_at,stage_results,resume_command) VALUES(?,'RUNNING',?,'{}',?)",(run_id,now(),resume_command));results={"preflight":preflight}
        else:results=json.loads(row["stage_results"]);conn.execute("UPDATE workflow_runs SET status='RUNNING',finished_at=NULL WHERE run_id=?",(run_id,))
    errors=0
    if "public_discovery" not in results:
        discovery=Discovery(db,config.settings)
        try:
            discovery_run=discovery.claim();out=discovery.execute(discovery_run);m2d.reconcile_discovery_run(out);metrics=out.get("metrics",{});stage_status="SKIPPED_COOLDOWN" if metrics.get("requests")==0 and metrics.get("skipped_sources") else out["status"];results["public_discovery"]={"status":stage_status,"run_id":discovery_run,"metrics":metrics}
        except RunBusy:results["public_discovery"]={"status":"SKIPPED","reason":"discovery_in_progress"}
        except Exception as error:errors+=1;results["public_discovery"]={"status":"FAILED","error":type(error).__name__}
        finally:discovery.close();_record(db,run_id,"PARTIAL",results,errors)
    if args.gmail_live and "gmail_intake" not in results:
        end=args.gmail_end or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")
        if args.gmail_start:start=args.gmail_start
        else:
            with db.transaction() as conn:last=conn.execute("SELECT interval_end FROM gmail_live_runs WHERE status='COMPLETED' ORDER BY interval_end DESC LIMIT 1").fetchone()
            lower=datetime.fromisoformat(last[0].replace("Z","+00:00"))-timedelta(minutes=15) if last else datetime.fromisoformat(end.replace("Z","+00:00"))-timedelta(hours=48)
            start=lower.isoformat().replace("+00:00","Z")
        reader=GmailOAuthReader(Path(args.gmail_root)/"client_secret.json",Path(args.gmail_root)/"compose_token.json")
        try:results["gmail_intake"]=ingest_live_interval(m2d,reader,start,end,max_pages=args.gmail_pages)
        except Exception as error:errors+=1;results["gmail_intake"]={"status":"FAILED","error":type(error).__name__,"interval_start":start,"interval_end":end}
        _record(db,run_id,"PARTIAL",results,errors)
    elif "gmail_intake" not in results:results["gmail_intake"]={"status":"SKIPPED","reason":"use --gmail-live for explicitly authorised intake"}
    from .email_opportunities import sync_email_opportunities
    _local_stage(db,run_id,results,'email_opportunities',lambda:sync_email_opportunities(db))
    if "official_details" not in results:
        details=Discovery(db,config.settings)
        try:
            outcome=details.execute_detail_checks(details.claim())
            results['official_details']={'status':outcome['status'],'run_id':outcome['id'],'metrics':outcome['metrics']}
        except Exception as error:
            errors+=1;results['official_details']={'status':'FAILED','error':type(error).__name__}
        finally:details.close();_record(db,run_id,'PARTIAL',results,errors)
    def verify_queue():
        created=m2d.seed_verification_tasks()
        return {'tasks_seeded':len(created),**m2d.execute_verification_tasks(limit=12)}
    _local_stage(db,run_id,results,'verification_queue',verify_queue)
    _local_stage(db,run_id,results,'contact_research',lambda:M3Engine(db).research_stored_contacts(limit=100))
    _local_stage(db,run_id,results,'application_preparation',lambda:M3Engine(db).prepare_queue())
    def export_workbook():
        exported=JobQueueWorkbook(m2d).export('CONSOLIDATED',Path(args.export_dir),run_id=run_id)
        return {'file':exported['path'].name,'checksum':exported['checksum'],'transfer':'NOT_UPLOADED'}
    _local_stage(db,run_id,results,'exports',export_workbook)
    from .coverage_report import report
    coverage_path=Path(args.export_dir)/'source-coverage.json';coverage_path.parent.mkdir(parents=True,exist_ok=True);coverage_path.write_text(json.dumps(report(db),indent=2),encoding='utf-8')
    results['exports']['source_coverage_file']=coverage_path.name
    results["postflight"]=_checks(db);pre=results.get("preflight",{}).get("counts",{});post=results["postflight"]["counts"];results["postflight"]["preserved"]={name:post.get(name,0)>=pre.get(name,0) for name in ("jobs","shortlists","history","packets","draft_operations")}
    stage_values=[v for k,v in results.items() if k not in {"preflight","postflight"}];errors=sum(v.get('status')=='FAILED' for v in stage_values);final="COMPLETED" if errors==0 and results["preflight"]["status"]==results["postflight"]["status"]=="PASS" and all(v.get("status") in {"COMPLETED","SKIPPED","SKIPPED_COOLDOWN"} for v in stage_values) else "PARTIAL";_record(db,run_id,final,results,errors,True)
    return {"run_id":run_id,"status":final,"stages":results,"resume_command":resume_command}

def main(argv=None):
    p=argparse.ArgumentParser(description="Run the local job workflow with durable stage outcomes")
    p.add_argument("--db",default="data/jobs.sqlite3");p.add_argument("--config",default="config/discovery.json");p.add_argument("--export-dir",default="data/exports")
    p.add_argument("--resume");p.add_argument("--gmail-live",action="store_true");p.add_argument("--gmail-root",default="data/gmail");p.add_argument("--gmail-start");p.add_argument("--gmail-end");p.add_argument("--gmail-pages",type=int,default=5)
    args=p.parse_args(argv);print(json.dumps(execute(args),indent=2));return 0

if __name__=="__main__":raise SystemExit(main())

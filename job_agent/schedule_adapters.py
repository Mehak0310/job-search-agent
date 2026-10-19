"""Explicit adapter assembly for the dormant scheduler; never enables a plan.

No reader, browser permission or configuration is inferred from imported text.
The existing adapters retain their own host limits, cooldowns and journals.
"""
from .policy_hooks import check


def assemble(db,config_path,*,gmail_reader=None,gmail_interval=None,allow_browser=False):
    def discovery(operation_key):
        check('scheduler','DISCOVERY')
        from .discovery import Discovery
        from .registry import Registry,load_config
        from .m2d import M2DEngine
        config=load_config(config_path);Registry(db).seed(config)
        worker=Discovery(db,config.settings)
        try:
            result=worker.execute(worker.claim())
            M2DEngine(db).reconcile_discovery_run(result)
            if result.get('status')!='COMPLETED':raise ValueError('discovery_run_requires_review')
            return result
        finally:worker.close()

    def gmail(operation_key):
        check('scheduler','GMAIL_INTAKE')
        if gmail_reader is None or not gmail_interval:raise ValueError('gmail_adapter_requires_authorized_reader_and_interval')
        from .gmail_local import ingest_live_interval
        from .m2d import M2DEngine
        start,end=gmail_interval()
        result=ingest_live_interval(M2DEngine(db),gmail_reader,start,end,max_pages=5)
        if result.get('status')!='COMPLETED':raise ValueError('gmail_run_requires_review')
        return result

    def verification(operation_key):
        check('scheduler','VERIFICATION')
        from .m2d import M2DEngine
        worker=M2DEngine(db);worker.seed_verification_tasks()
        return worker.execute_verification_tasks(limit=12)

    def preparation(operation_key):
        check('scheduler','PREPARATION')
        if not allow_browser:raise ValueError('browser_preparation_requires_explicit_runtime_permission')
        from .browser_store import BrowserStore
        from .browser_applications import launch_worker
        with db.transaction() as conn:
            if conn.execute("SELECT 1 FROM browser_workflows WHERE state IN ('QUEUED','RUNNING')").fetchone():raise ValueError('workflow_already_running')
        batch=BrowserStore(db).batch(limit=5)
        if batch['selected']:batch['worker_pid']=launch_worker(db,batch['batch_id'])
        return batch

    def notifications(operation_key):
        check('scheduler','NOTIFICATIONS')
        from .orchestration import record_progress
        with db.transaction() as conn:ids=[r[0] for r in conn.execute("SELECT id FROM browser_applications WHERE application_outcome='NOT_SUBMITTED'")]
        for identifier in ids:record_progress(db,identifier)
        return {'inspected':len(ids)}

    return {'DISCOVERY':discovery,'GMAIL_INTAKE':gmail,'VERIFICATION':verification,'PREPARATION':preparation,'NOTIFICATIONS':notifications}

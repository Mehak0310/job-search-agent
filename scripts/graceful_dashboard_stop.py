"""Signal only an identified, exclusive dashboard console. Never force-kills."""
import argparse,ctypes,json,os,sqlite3,time
from pathlib import Path
import httpx


def main():
    p=argparse.ArgumentParser();p.add_argument('--pid',type=int,required=True);p.add_argument('--parent',type=int,required=True);args=p.parse_args()
    root=Path.cwd().resolve();health=httpx.get('http://127.0.0.1:8000/api/health',timeout=5).json()['runtime']
    assert health['pid']==args.pid and Path(health['source_root']).resolve()==root/'job_agent'
    assert Path(health['database_path']).resolve()==root/'data/jobs.sqlite3'
    assert (root/'data/r2-activation/pre-activation.sqlite3').is_file()
    with sqlite3.connect('file:data/jobs.sqlite3?mode=ro',uri=True) as c:assert not c.execute("SELECT 1 FROM browser_workflows WHERE state IN ('QUEUED','RUNNING')").fetchone()
    kernel=ctypes.WinDLL('kernel32',use_last_error=True);kernel.FreeConsole()
    assert kernel.AttachConsole(args.pid),'Target console unavailable; no signal sent'
    members=(ctypes.c_ulong*32)();count=kernel.GetConsoleProcessList(members,32)
    actual=set(members[:count]);expected={args.pid,args.parent,os.getpid()}
    assert count<=32 and actual==expected,'Console not exclusive; no signal sent'
    assert kernel.SetConsoleCtrlHandler(None,True)
    assert kernel.GenerateConsoleCtrlEvent(0,0)
    time.sleep(.2);kernel.FreeConsole()
    print(json.dumps({'graceful_signal_sent':True,'verified_dashboard_pid':args.pid,'unrelated_processes_signaled':False}))


if __name__=='__main__':main()

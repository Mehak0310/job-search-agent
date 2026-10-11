"""Reviewable Windows Task Scheduler setup without changing execution policy."""
import argparse
import getpass
import json
import os
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

NS = "http://schemas.microsoft.com/windows/2004/02/mit/task"
ET.register_namespace("", NS)


def task_plan(workspace: Path, india_time="08:00", catch_up=False, task_name="AIJobSearchDiscovery2A") -> dict:
    hour, minute = (int(part) for part in india_time.split(":"))
    if not 0 <= hour <= 23 or not 0 <= minute <= 59 or not task_name or any(c in task_name for c in "\\/\x00"):
        raise ValueError("invalid_schedule")
    workspace = workspace.resolve()
    python = workspace / ".venv/Scripts/python.exe"
    config = workspace / "config/discovery.json"
    if not python.is_file() or not config.is_file():
        raise ValueError("missing_project_environment")
    ist = timezone(timedelta(hours=5, minutes=30))
    current = datetime.now(ist)
    start = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if start <= current:
        start += timedelta(days=1)
    account = (os.environ.get("USERDOMAIN", "") + "\\" + getpass.getuser()).lstrip("\\")
    return {"task_name": task_name, "description": f"Public job discovery for {workspace} (Milestone 2A)", "user_id": account, "executable": str(python), "arguments": f'-m job_agent.discover --config "{config}" --db "{workspace / "data/jobs.sqlite3"}"', "working_directory": str(workspace), "start_boundary": start.isoformat(), "catch_up": catch_up, "requires_logged_in_user": True}


def task_xml(plan: dict) -> str:
    root = ET.Element(f"{{{NS}}}Task", version="1.2")
    def node(parent, name, value=None, **attrs):
        child = ET.SubElement(parent, f"{{{NS}}}{name}", attrs)
        if value is not None:
            child.text = str(value)
        return child
    registration = node(root, "RegistrationInfo")
    node(registration, "Description", plan["description"])
    trigger = node(node(root, "Triggers"), "CalendarTrigger")
    node(trigger, "StartBoundary", plan["start_boundary"])
    node(trigger, "Enabled", "true")
    node(node(trigger, "ScheduleByDay"), "DaysInterval", "1")
    principal = node(node(root, "Principals"), "Principal", id="Author")
    node(principal, "UserId", plan["user_id"])
    node(principal, "LogonType", "InteractiveToken")
    node(principal, "RunLevel", "LeastPrivilege")
    settings = node(root, "Settings")
    node(settings, "MultipleInstancesPolicy", "IgnoreNew")
    node(settings, "DisallowStartIfOnBatteries", "false")
    node(settings, "StopIfGoingOnBatteries", "false")
    node(settings, "StartWhenAvailable", str(plan["catch_up"]).lower())
    node(settings, "ExecutionTimeLimit", "PT15M")
    action = node(node(root, "Actions", Context="Author"), "Exec")
    node(action, "Command", plan["executable"])
    node(action, "Arguments", plan["arguments"])
    node(action, "WorkingDirectory", plan["working_directory"])
    return '<?xml version="1.0" encoding="UTF-16"?>\n' + ET.tostring(root, encoding="unicode")


def register_task(plan: dict, run=subprocess.run) -> None:
    existing = run(["schtasks.exe", "/Query", "/TN", plan["task_name"], "/XML"], capture_output=True, check=False)
    if existing.returncode == 0:
        try:
            description = ET.fromstring(existing.stdout).find(f"{{{NS}}}RegistrationInfo/{{{NS}}}Description")
        except ET.ParseError:
            raise ValueError("unrecognized_existing_task") from None
        if description is None or description.text != plan["description"]:
            raise ValueError("unrelated_task_name_collision")
    # Called only after explicit --register; no persistent artifacts in preview mode.
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "discovery-task.xml"
        path.write_text(task_xml(plan), encoding="utf-16")
        command = ["schtasks.exe", "/Create", "/TN", plan["task_name"], "/XML", str(path)]
        if existing.returncode == 0:
            command.append("/F")
        run(command, check=True, capture_output=True, text=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Preview Windows discovery task; register only with explicit approval")
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--catch-up", action="store_true")
    parser.add_argument("--india-time", default="08:00")
    parser.add_argument("--task-name", default="AIJobSearchDiscovery2A")
    parser.add_argument("--workspace", default=str(Path(__file__).resolve().parent.parent))
    args = parser.parse_args(argv)
    plan = task_plan(Path(args.workspace), args.india_time, args.catch_up, args.task_name)
    print(json.dumps(plan | {"will_register": args.register}, indent=2))
    if args.register:
        register_task(plan)


if __name__ == "__main__":
    main()

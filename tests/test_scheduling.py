import json
import runpy
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

import pytest

from job_agent.scheduling import NS, main, register_task, task_plan, task_xml


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / ".venv/Scripts").mkdir(parents=True)
    (tmp_path / ".venv/Scripts/python.exe").touch()
    (tmp_path / "config").mkdir()
    (tmp_path / "config/discovery.json").write_text('{}')
    return tmp_path


def test_preview_ist_and_catchup_xml(workspace, capsys):
    plan = task_plan(workspace, catch_up=True)
    assert plan["start_boundary"].endswith("08:00:00+05:30")
    assert plan["executable"] == str(workspace / ".venv/Scripts/python.exe")
    root = ET.fromstring(task_xml(plan))
    assert root.find(f"{{{NS}}}Settings/{{{NS}}}StartWhenAvailable").text == "true"
    assert root.find(f"{{{NS}}}Principals/{{{NS}}}Principal/{{{NS}}}LogonType").text == "InteractiveToken"
    with patch("job_agent.scheduling.register_task") as register:
        main(["--workspace", str(workspace), "--catch-up"])
        register.assert_not_called()
    assert not json.loads(capsys.readouterr().out)["will_register"]


@pytest.mark.parametrize("time,name", [("25:00", "task"), ("08:61", "task"), ("08:00", "bad/name")])
def test_invalid_schedule(workspace, time, name):
    with pytest.raises(ValueError):
        task_plan(workspace, time, task_name=name)


def test_missing_environment(tmp_path):
    with pytest.raises(ValueError, match="missing_project_environment"):
        task_plan(tmp_path)


def test_idempotent_registration_with_mocked_schtasks(workspace):
    plan = task_plan(workspace)
    calls = []
    def fake_run(command, **kwargs):
        calls.append(command)
        if "/Query" in command:
            return subprocess.CompletedProcess(command, 0, stdout=task_xml(plan).encode("utf-16"))
        path = Path(command[command.index("/XML") + 1])
        assert path.read_text(encoding="utf-16").startswith("<?xml")
        assert ET.fromstring(path.read_bytes()).tag == f"{{{NS}}}Task"
        assert "/F" in command and kwargs["check"]
        return subprocess.CompletedProcess(command, 0)
    register_task(plan, fake_run)
    assert len(calls) == 2 and all(command[0] == "schtasks.exe" for command in calls)


@pytest.mark.parametrize("xml,code", [("invalid", "unrecognized_existing_task"), ('<Task xmlns="' + NS + '"><RegistrationInfo><Description>unrelated</Description></RegistrationInfo></Task>', "unrelated_task_name_collision")])
def test_do_not_overwrite_unrelated_task(workspace, xml, code):
    with pytest.raises(ValueError, match=code):
        register_task(task_plan(workspace), lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=xml))


def test_explicit_registration_and_entrypoint_preview(workspace, monkeypatch):
    with patch("job_agent.scheduling.register_task") as register:
        main(["--workspace", str(workspace), "--register"])
        register.assert_called_once()
    monkeypatch.delitem(sys.modules, "job_agent.scheduling", raising=False)
    monkeypatch.setattr(sys, "argv", ["schedule", "--workspace", str(workspace)])
    runpy.run_module("job_agent.scheduling", run_name="__main__")


def test_failed_query_never_forces_overwrite(workspace):
    def fake_run(command, **kwargs):
        if "/Query" in command:
            return subprocess.CompletedProcess(command, 1, stdout="")
        assert "/F" not in command
        return subprocess.CompletedProcess(command, 0)
    register_task(task_plan(workspace), fake_run)

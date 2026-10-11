import json
import runpy
import sys
from unittest.mock import patch

from job_agent.discover import main
from job_agent.discovery import RunBusy


def test_setup_only_is_offline(tmp_path, capsys):
    config = tmp_path / "config.json"
    config.write_text('{"sources": []}')
    assert main(["--config", str(config), "--db", str(tmp_path / "jobs.sqlite3"), "--sync-sources", "--setup-only"]) == 0
    assert json.loads(capsys.readouterr().out)["sources"] == []


def test_manual_cli_terminal_and_busy(tmp_path, capsys):
    config = tmp_path / "config.json"
    config.write_text('{"sources": []}')
    args = ["--config", str(config), "--db", str(tmp_path / "jobs.sqlite3")]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "COMPLETED"
    with patch("job_agent.discover.Discovery.claim", side_effect=RunBusy()):
        assert main(args) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "SKIPPED"
    with patch("job_agent.discover.Discovery.execute", return_value={"status": "PARTIAL"}):
        assert main(args) == 1


def test_module_cli_entrypoint_offline(tmp_path, monkeypatch):
    config = tmp_path / "config.json"
    config.write_text('{"sources": []}')
    monkeypatch.delitem(sys.modules, "job_agent.discover", raising=False)
    monkeypatch.setattr(sys, "argv", ["discover", "--config", str(config), "--db", str(tmp_path / "jobs.sqlite3")])
    with patch("sys.exit"):
        import pytest
        with pytest.raises(SystemExit) as exit_info:
            runpy.run_module("job_agent.discover", run_name="__main__")
    assert exit_info.value.code == 0

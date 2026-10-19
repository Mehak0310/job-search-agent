import runpy
import sys
from unittest.mock import patch

import pytest


def test_launcher_is_loopback_only(tmp_path, monkeypatch):
    from job_agent.__main__ import main
    monkeypatch.chdir(tmp_path)
    with patch("job_agent.__main__.uvicorn.run") as run:
        main([])
    assert run.call_args.kwargs == {"host": "127.0.0.1", "port": 8000,"loop":"job_agent.server_runtime:new_server_loop"}


def test_module_execution_binds_loopback(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delitem(sys.modules, "job_agent.__main__", raising=False)
    monkeypatch.setattr(sys, "argv", ["job_agent", "--port", "8001"])
    with patch("uvicorn.run") as run:
        runpy.run_module("job_agent", run_name="__main__")
    assert run.call_args.kwargs == {"host": "127.0.0.1", "port": 8001,"loop":"job_agent.server_runtime:new_server_loop"}


@pytest.mark.parametrize("port", ["80", "65536", "abc"])
def test_invalid_port(port):
    from job_agent.__main__ import main
    with pytest.raises(SystemExit):
        main(["--port", port])

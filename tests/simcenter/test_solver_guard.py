import subprocess
from types import SimpleNamespace

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter import solver_guard


@pytest.mark.parametrize(
    "stdout,code,expected",
    [
        (b"1", 0, "NX_SIM_SOLVER_BUSY"),
        (b"9", 0, "NX_SIM_SOLVER_BUSY"),
        (b"", 0, "NX_SIM_SOLVER_STATE_UNKNOWN"),
        (b"0", 2, "NX_SIM_SOLVER_STATE_UNKNOWN"),
        (b"0\nerror", 0, "NX_SIM_SOLVER_STATE_UNKNOWN"),
        (b"-1", 0, "NX_SIM_SOLVER_STATE_UNKNOWN"),
        (b"1" * 100, 0, "NX_SIM_SOLVER_STATE_UNKNOWN"),
    ],
)
def test_busy_and_uncertain_queries_never_allow_mutation(monkeypatch, stdout, code, expected):
    monkeypatch.setattr(
        solver_guard.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(stdout=stdout, returncode=code),
    )
    with pytest.raises(NXToolError) as raised:
        solver_guard.require_solver_idle()
    assert raised.value.code == expected
    assert raised.value.details["mutation_outcome"] == "not_started"


@pytest.mark.parametrize(
    "error", [OSError("sensitive diagnostic"), subprocess.TimeoutExpired("secret command", 15)]
)
def test_query_exceptions_are_structured_and_sanitized(monkeypatch, error):
    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(solver_guard.subprocess, "run", fail)
    with pytest.raises(NXToolError) as raised:
        solver_guard.require_solver_idle()
    assert raised.value.code == "NX_SIM_SOLVER_STATE_UNKNOWN"
    assert "secret" not in str(raised.value.details)
    assert "sensitive" not in str(raised.value)


def test_idle_query_is_bounded_and_reports_snapshot_limit(monkeypatch):
    def run(args, **kwargs):
        assert kwargs["timeout"] == 15 and kwargs["capture_output"]
        assert "shell" not in kwargs
        assert "Stop-Process" not in args[-1]
        return SimpleNamespace(stdout=b"0", returncode=0)

    monkeypatch.setattr(solver_guard.subprocess, "run", run)
    assert "not an atomic lock" in solver_guard.require_solver_idle()["exclusion"]

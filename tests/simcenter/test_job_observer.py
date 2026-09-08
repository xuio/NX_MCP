import os
from datetime import datetime

import pytest
from test_preparation import context  # noqa: F401

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter import job_observer, preparation
from nx_mcp.simcenter.jobs import JobStore
from nx_mcp.simcenter.solver_manifest import preserve_input


@pytest.fixture
def observed(context, monkeypatch):  # noqa: F811
    session, workspace, sim, rows, calls = context
    preparation.prepare_solve(session, workspace, sim, "observe-01")
    store = JobStore(workspace)
    job = store.inspect("observe-01")
    deck = workspace.resolve(job["manifest"]["prepared_input"]["input"]["path"])
    preserve_input(store._directory("observe-01"), "before-launch", deck.read_bytes())
    intent = store.transition(
        "observe-01", expected_revision=0, state="launch_requested", evidence={"fixture": True}
    )
    store.transition("observe-01", expected_revision=1, state="launch_returned", evidence={"fixture": True})
    timestamp = datetime.fromisoformat(intent["record"]["observed_at"]).timestamp() + 1
    for suffix, data in (
        (".log", b"\n Solve completed at:\n time\n"),
        (".bun", b"native result fixture"),
    ):
        path = deck.with_suffix(suffix)
        path.write_bytes(data)
        os.utime(path, (timestamp, timestamp))
    monkeypatch.setattr(job_observer, "require_solver_idle", lambda: {"solver_processes": 0})
    return workspace, store, deck


def test_terminal_observation_is_durable_and_repeat_is_readonly(observed):
    workspace, store, deck = observed
    result = job_observer.observe_terminal(workspace, "observe-01")
    assert result["state"] == "solver_exited" and result["job_state_changed"]
    assert result["evidence"]["process_exit_code"] is None
    assert result["evidence"]["numerical_convergence"] == "not_established"
    assert not job_observer.observe_terminal(workspace, "observe-01")["job_state_changed"]
    assert store.inspect("observe-01")["revision"] == 3


def test_old_results_cannot_advance_job(observed):
    workspace, store, deck = observed
    os.utime(deck.with_suffix(".bun"), (1, 1))
    result = job_observer.observe_terminal(workspace, "observe-01")
    assert not result["job_state_changed"] and result["state"] == "launch_returned"


def test_busy_solver_preserves_launch_state(observed, monkeypatch):
    workspace, store, deck = observed

    def busy():
        raise NXToolError("NX_SIM_SOLVER_BUSY", "busy")

    monkeypatch.setattr(job_observer, "require_solver_idle", busy)
    assert job_observer.observe_terminal(workspace, "observe-01")["reason"] == "NX_SIM_SOLVER_BUSY"
    assert store.inspect("observe-01")["revision"] == 2


def test_input_mismatch_retains_job_and_gate(observed):
    workspace, store, deck = observed
    deck.write_text('<SolutionFile changed="true"><ElementList/><NodeList/></SolutionFile>')
    with pytest.raises(NXToolError) as error:
        job_observer.observe_terminal(workspace, "observe-01")
    assert error.value.code == "NX_SIM_INPUT_CHANGED"
    assert store.inspect("observe-01")["revision"] == 2

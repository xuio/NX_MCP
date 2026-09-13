import pytest
from test_job_observer import observed  # noqa: F401
from test_preparation import context  # noqa: F401

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter import job_observer, launch_gate, solver_guard


def test_verified_release_preserves_outputs_and_replays(observed, monkeypatch):  # noqa: F811
    workspace, store, deck = observed
    job_observer.observe_terminal(workspace, "observe-01")
    launch_gate.claim_launch_gate(store, "observe-01")
    monkeypatch.setattr(solver_guard, "require_solver_idle", lambda: {})
    result = launch_gate.release_launch_gate(store, "observe-01")
    assert result["released"] and deck.with_suffix(".bun").is_file()
    assert not workspace.resolve(".nx-sim-launch-owner.json").exists()
    assert launch_gate.release_launch_gate(store, "observe-01")["replayed"]
    store.reserve("next-job", {"fixture": True})
    launch_gate.claim_launch_gate(store, "next-job")
    assert launch_gate.release_launch_gate(store, "observe-01")["other_gate_untouched"]
    with pytest.raises(NXToolError, match="never relaunch"):
        launch_gate.claim_launch_gate(store, "observe-01")


def test_unverified_terminal_does_not_release(observed):  # noqa: F811
    workspace, store, deck = observed
    launch_gate.claim_launch_gate(store, "observe-01")
    with pytest.raises(NXToolError) as error:
        launch_gate.release_launch_gate(store, "observe-01")
    assert error.value.code == "NX_SIM_TERMINAL_UNVERIFIED"
    assert workspace.resolve(".nx-sim-launch-owner.json").exists()


def test_changed_result_does_not_release(observed, monkeypatch):  # noqa: F811
    workspace, store, deck = observed
    job_observer.observe_terminal(workspace, "observe-01")
    launch_gate.claim_launch_gate(store, "observe-01")
    deck.with_suffix(".bun").write_bytes(b"changed")
    with pytest.raises(NXToolError) as error:
        launch_gate.release_launch_gate(store, "observe-01")
    assert error.value.code == "NX_SIM_TERMINAL_CHANGED"
    assert workspace.resolve(".nx-sim-launch-owner.json").exists()


def test_competing_gate_operation_is_excluded(observed):  # noqa: F811
    workspace, store, deck = observed
    with launch_gate._gate_lock(workspace):
        with pytest.raises(NXToolError) as error:
            launch_gate.claim_launch_gate(store, "observe-01")
        assert error.value.code == "NX_SIM_LAUNCH_GATE_BUSY"


@pytest.mark.parametrize("changed", ["none", "result_appeared", "solver_busy", "input", "log"])
def test_failed_run_without_result_release_rechecks_evidence(observed, monkeypatch, changed):  # noqa: F811
    import os

    workspace, store, deck = observed
    log = deck.with_suffix(".log")
    stamp = log.stat().st_mtime
    log.write_text("| FATAL ERROR ENCOUNTERED |\n\n Solve completed at:\n time\n")
    os.utime(log, (stamp, stamp))
    deck.with_suffix(".bun").unlink()
    report = job_observer.observe_terminal(workspace, "observe-01")
    assert report["state"] == "solver_exited"
    assert report["evidence"]["result"] is None
    assert report["evidence"]["solver_log_diagnostic"]["state"] == "failed"
    launch_gate.claim_launch_gate(store, "observe-01")
    monkeypatch.setattr(solver_guard, "require_solver_idle", lambda: {})
    if changed == "result_appeared":
        deck.with_suffix(".bun").write_bytes(b"late result")
    elif changed == "solver_busy":

        def busy():
            raise NXToolError("NX_SIM_SOLVER_BUSY", "busy")

        monkeypatch.setattr(solver_guard, "require_solver_idle", busy)
    elif changed == "input":
        deck.write_text('<SolutionFile changed="true"><ElementList/><NodeList/></SolutionFile>')
    elif changed == "log":
        log.write_text("changed")
    if changed != "none":
        with pytest.raises(NXToolError):
            launch_gate.release_launch_gate(store, "observe-01")
        assert workspace.resolve(".nx-sim-launch-owner.json").exists()
    else:
        assert launch_gate.release_launch_gate(store, "observe-01")["released"]
        assert not deck.with_suffix(".bun").exists()
        assert log.exists()
        assert launch_gate.release_launch_gate(store, "observe-01")["replayed"]

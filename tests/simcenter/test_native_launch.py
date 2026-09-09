import sys
from types import SimpleNamespace as NS

import pytest
from test_preparation import context  # noqa: F401

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter import native_launch, preparation
from nx_mcp.simcenter.jobs import JobStore


@pytest.fixture
def launch_context(context, monkeypatch, request):  # noqa: F811
    session, workspace, sim, rows, exports = context
    session.Parts.BaseDisplay = sim
    sim.Simulation.ActiveSolution.AnalysisType = getattr(request, "param", "Thermal")
    preparation.prepare_solve(session, workspace, sim, "native-01")
    monkeypatch.setattr(native_launch, "require_solver_idle", lambda: None)
    monkeypatch.setattr(native_launch, "inspect_direct", preparation.inspect_direct)
    monkeypatch.setattr(
        native_launch, "capture_analysis_thermal_state", preparation.capture_analysis_thermal_state
    )
    cae = sys.modules["NXOpen.CAE"]
    cae.SimSolutionSolveOption = NS(Solve="solve")
    cae.SimSolutionSetupCheckOption = NS(CompleteCheckAndOutputErrors="check")
    props = {"Foreground": True}
    solution = sim.Simulation.ActiveSolution
    solution.PropertyTable = NS(
        GetBooleanPropertyValue=lambda k: props[k],
        SetBooleanPropertyValue=lambda k, v: props.update({k: v}),
    )
    calls = []

    def solve(*args):
        assert JobStore(workspace).inspect("native-01")["state"] == "launch_requested"
        assert props["Foreground"] is False
        calls.append(args)

    solution.Solve = solve
    return session, workspace, sim, rows, props, calls


@pytest.mark.parametrize("launch_context", ["Thermal", "Coupled Thermal-Flow"], indirect=True)
def test_durable_intent_and_background_launch_replay(launch_context):
    session, workspace, sim, rows, props, calls = launch_context
    result = native_launch.launch_prepared(session, workspace, sim, "native-01")
    assert result["state"] == "launch_returned" and calls == [("solve", "check")]
    assert props["Foreground"] is True
    rows[0]["modified"] = True
    result = native_launch.launch_prepared(session, workspace, sim, "native-01")
    assert result["replayed"] and len(calls) == 1


def test_changed_input_rejects_before_intent(launch_context):
    session, workspace, sim, rows, props, calls = launch_context
    (workspace.root / "run/input.xml").write_text("<broken/>")
    with pytest.raises(NXToolError) as error:
        native_launch.launch_prepared(session, workspace, sim, "native-01")
    assert error.value.code == "NX_SIM_INPUT_CHANGED" and not calls
    assert JobStore(workspace).inspect("native-01")["state"] == "accepted"


def test_native_error_is_uncertain_and_never_retried(launch_context):
    session, workspace, sim, rows, props, calls = launch_context

    def fail(*args):
        calls.append(args)
        raise RuntimeError("solver API failed after possible dispatch")

    sim.Simulation.ActiveSolution.Solve = fail
    with pytest.raises(NXToolError) as error:
        native_launch.launch_prepared(session, workspace, sim, "native-01")
    assert error.value.code == "NX_SIM_LAUNCH_UNCERTAIN" and props["Foreground"] is True
    result = native_launch.launch_prepared(session, workspace, sim, "native-01")
    assert result["state"] == "launch_uncertain" and len(calls) == 1


def test_foreign_solution_rejected_before_intent(launch_context):
    session, workspace, sim, rows, props, calls = launch_context
    sim.Simulation.ActiveSolution.Name = "other"
    with pytest.raises(NXToolError) as error:
        native_launch.launch_prepared(session, workspace, sim, "native-01")
    assert error.value.code == "NX_SIM_SOLUTION_CHANGED" and not calls


def test_pending_dispatch_excludes_a_different_job(launch_context):
    from nx_mcp.simcenter.launch_gate import claim_launch_gate

    session, workspace, sim, rows, props, calls = launch_context
    store = JobStore(workspace)
    store.reserve("other-job", {"isolated": True})
    claim_launch_gate(store, "other-job")
    with pytest.raises(NXToolError) as error:
        native_launch.launch_prepared(session, workspace, sim, "native-01")
    assert error.value.code == "NX_SIM_LAUNCH_GATE_BUSY" and not calls
    assert store.inspect("native-01")["state"] == "accepted"


def test_live_thermal_change_rejects_before_launch_intent(launch_context, monkeypatch):
    session, workspace, sim, rows, props, calls = launch_context
    monkeypatch.setattr(
        native_launch,
        "capture_analysis_thermal_state",
        lambda sim: {"adapter": 1, "scope": "test", "owner_path": sim.FullPath, "sha256": "b" * 64},
    )
    with pytest.raises(NXToolError) as error:
        native_launch.launch_prepared(session, workspace, sim, "native-01")
    assert error.value.code == "NX_SIM_LIVE_STATE_CHANGED"
    assert not calls and props["Foreground"]
    assert JobStore(workspace).inspect("native-01")["state"] == "accepted"


def test_changed_mesh_rejected_before_launch_intent(launch_context, monkeypatch):
    from nx_mcp.simcenter import mesh_guard

    session, workspace, sim, rows, props, calls = launch_context
    original = mesh_guard.capture

    def changed(sim, maximum_entities=200000):
        result = original(sim, maximum_entities)
        result["sha256"] = "b" * 64
        return result

    monkeypatch.setattr(mesh_guard, "capture", changed)
    with pytest.raises(NXToolError) as error:
        native_launch.launch_prepared(session, workspace, sim, "native-01")
    assert error.value.code == "NX_SIM_MESH_STATE_CHANGED"
    assert not calls and props["Foreground"] is True
    assert JobStore(workspace).inspect("native-01")["state"] == "accepted"


def test_launched_job_replay_does_not_inspect_current_mesh(launch_context, monkeypatch):
    from nx_mcp.simcenter import mesh_guard

    session, workspace, sim, rows, props, calls = launch_context
    native_launch.launch_prepared(session, workspace, sim, "native-01")

    def forbidden(*args):
        raise AssertionError("Replay inspected mutable mesh")

    monkeypatch.setattr(mesh_guard, "verify_manifest", forbidden)
    assert native_launch.launch_prepared(session, workspace, sim, "native-01")["replayed"]
    assert len(calls) == 1


def test_missing_mesh_baseline_is_not_invented(launch_context, monkeypatch):
    from nx_mcp.simcenter.mesh_guard import verify_manifest

    session, workspace, sim, rows, props, calls = launch_context
    with pytest.raises(NXToolError) as error:
        verify_manifest(sim, {"preparation_adapter": 1})
    assert error.value.code == "NX_SIM_MESH_STATE_MISSING"
    assert not calls

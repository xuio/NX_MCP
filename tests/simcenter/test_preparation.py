import sys
from types import ModuleType
from types import SimpleNamespace as NS

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter import preparation
from nx_mcp.simcenter.jobs import JobStore
from nx_mcp.workspace import Workspace


@pytest.fixture
def context(tmp_path, monkeypatch):
    cae = ModuleType("NXOpen.CAE")
    cae.SimPart = type("SimPart", (), {})
    nx = ModuleType("NXOpen")
    nx.CAE = cae
    monkeypatch.setitem(sys.modules, "NXOpen", nx)
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)
    root = tmp_path / "run"
    root.mkdir()
    sim = cae.SimPart()
    sim.FullPath = str(root / "case.sim")
    (root / "case.sim").write_bytes(b"saved simulation")
    solution = NS(Name="Thermal", SolverType="NX MULTIPHYSICS", AnalysisType="Thermal")
    sim.Simulation = NS(ActiveSolution=solution, Solutions=[solution])
    session = NS(Parts=NS(BaseWork=sim))
    rows = [{"path": sim.FullPath, "modified": False, "fully_loaded": True, "file_state": "exists"}]
    monkeypatch.setattr(
        preparation,
        "inspect_direct",
        lambda *args: {
            "rows": rows,
            "unresolved": [],
            "scope": "direct",
            "excluded": "external files",
        },
    )
    monkeypatch.setattr(preparation, "require_solver_idle", lambda: None)
    monkeypatch.setattr(
        preparation,
        "capture_analysis_thermal_state",
        lambda sim: {"adapter": 1, "scope": "test", "owner_path": sim.FullPath, "sha256": "a" * 64},
    )
    calls = []

    def export(*args):
        calls.append(1)
        path = root / "input.xml"
        path.write_text(
            "<SolutionFile><ElementList><Set><E>1</E></Set></ElementList></SolutionFile>"
        )
        return {"input_path": str(path), "validation": {"mesh_counts": {"elements": 1}}}

    monkeypatch.setattr(preparation, "export_flow_input", export)
    return session, Workspace(tmp_path), sim, rows, calls


def test_prepared_job_replays_and_rejects_changed_input(context):
    session, workspace, sim, rows, calls = context
    result = preparation.prepare_solve(session, workspace, sim, "run-01")
    assert result["state"] == "accepted" and not result["solver_launched_by_call"]
    assert preparation.prepare_solve(session, workspace, sim, "run-01")["replayed"]
    assert len(calls) == 1
    workspace.resolve(result["input_path"]).write_text("<different/>")
    with pytest.raises(NXToolError) as error:
        preparation.prepare_solve(session, workspace, sim, "run-01")
    assert error.value.code == "NX_SIM_INPUT_CHANGED" and len(calls) == 1


def test_unsaved_dependency_rejected_before_export(context):
    session, workspace, sim, rows, calls = context
    rows[0]["modified"] = True
    with pytest.raises(NXToolError, match="Save and fully load"):
        preparation.prepare_solve(session, workspace, sim, "run-01")
    assert not calls and not (workspace.root / "simcenter-jobs").exists()


def test_changed_dependency_after_export_retains_files_without_job(context, monkeypatch):
    session, workspace, sim, rows, calls = context
    original = preparation.export_flow_input

    def changed(*args):
        result = original(*args)
        workspace.resolve(sim.FullPath).write_bytes(b"changed during export")
        return result

    monkeypatch.setattr(preparation, "export_flow_input", changed)
    with pytest.raises(NXToolError) as error:
        preparation.prepare_solve(session, workspace, sim, "run-01")
    assert error.value.code == "NX_SIM_PREPARATION_INCOMPLETE"
    assert error.value.details["cause_code"] == "NX_SIM_REVISION_CHANGED"
    assert (workspace.root / "run/input.xml").exists()
    assert not (workspace.root / "simcenter-jobs").exists()


def test_launched_identity_never_exports_again(context):
    session, workspace, sim, rows, calls = context
    preparation.prepare_solve(session, workspace, sim, "run-01")
    store = JobStore(workspace)
    store.transition(
        "run-01", expected_revision=0, state="launch_requested", evidence={"test": True}
    )
    rows[0]["modified"] = True
    result = preparation.prepare_solve(session, workspace, sim, "run-01")
    assert result["state"] == "launch_requested" and not result["preparation_revalidated"]
    assert len(calls) == 1


def test_job_folder_inside_output_rejected(context):
    session, workspace, sim, rows, calls = context
    with pytest.raises(NXToolError, match="outside"):
        preparation.prepare_solve(session, workspace, sim, "run-01", "run/jobs")
    assert not calls

import sys
from types import ModuleType
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.internal_fan import inspect_schema


@pytest.fixture
def rig(monkeypatch):
    nx, cae = ModuleType("NXOpen"), ModuleType("NXOpen.CAE")
    cae.SimPart = type("SimPart", (), {})
    nx.Session = NS(MarkVisibility=NS(Invisible=0))
    nx.CAE = cae
    monkeypatch.setitem(sys.modules, "NXOpen", nx)
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)
    monkeypatch.setattr("nx_mcp.simcenter.solver_guard.require_solver_idle", lambda: {"idle": True})
    sim = cae.SimPart()
    sim.Expressions, sim.IsModified, sim.FieldManager = [], False, NS(Fields=[])
    props = NS(
        GetPropertyCount=lambda: 1,
        GetPropertyNameByIndex=lambda i: "Mode Option",
        GetPropertyDescriptorName=lambda k: (
            "Mode Option\nVelocity\nVelocity Vector\nMass Flow\nVolume Flow\nFan Curve"
        ),
    )
    builder = NS(PropertyTable=props, TargetSetManager=NS(TargetSetCount=1), Destroy=Mock())
    sim.Simulation = NS(
        SimulationObjects=[],
        ActiveSolution=NS(
            SolverType="NX MULTIPHYSICS", AnalysisType="Coupled Thermal-Flow", GetBcs=lambda: []
        ),
        CreateBcBuilderForSimulationObjectDescriptor=Mock(return_value=builder),
    )
    session = NS(
        Parts=NS(BaseWork=sim),
        SetUndoMark=Mock(return_value=42),
        UndoToMark=Mock(),
        DeleteUndoMark=Mock(),
    )
    monkeypatch.setattr(
        "nx_mcp.simcenter.properties.read_properties",
        lambda p, n: [{"name": "Mode Option", "value": 0}],
    )
    return session, sim, builder


def test_inspection_is_uncommitted_and_cleaned_up(rig):
    session, sim, builder = rig
    result = inspect_schema(session, sim)
    assert result["target_set_count"] == 1 and result["state_restored"]
    assert result["committed_boundaries"] == 0 and not result["numerical_acceptance"]
    builder.Destroy.assert_called_once()
    session.UndoToMark.assert_called_once_with(42, None)
    session.DeleteUndoMark.assert_called_once_with(42, None)


def test_wrong_work_part_never_creates_builder(rig):
    session, sim, builder = rig
    session.Parts.BaseWork = None
    with pytest.raises(NXToolError, match="Activate"):
        inspect_schema(session, sim)
    session.SetUndoMark.assert_not_called()


def test_builder_failure_rolls_back(rig):
    session, sim, builder = rig
    sim.Simulation.CreateBcBuilderForSimulationObjectDescriptor.side_effect = RuntimeError(
        "unavailable"
    )
    with pytest.raises(NXToolError) as exc:
        inspect_schema(session, sim)
    assert exc.value.details["mutation_outcome"] == "rolled_back"
    session.UndoToMark.assert_called_once()


def test_changed_inventory_is_reported_as_partial(rig):
    session, sim, builder = rig
    builder.Destroy.side_effect = lambda: sim.Expressions.append(NS(Tag=123))
    with pytest.raises(NXToolError) as exc:
        inspect_schema(session, sim)
    assert exc.value.code == "NX_SIM_RECOVERY_INCOMPLETE"
    assert exc.value.details["mutation_outcome"] == "partial"


def test_destroy_error_does_not_skip_undo(rig):
    session, sim, builder = rig
    builder.Destroy.side_effect = RuntimeError("destroy failed")
    with pytest.raises(NXToolError):
        inspect_schema(session, sim)
    session.UndoToMark.assert_called_once()

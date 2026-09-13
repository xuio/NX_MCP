import sys
from types import ModuleType
from types import SimpleNamespace as NS

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.steady_flow_timestep import configure_physical_step


@pytest.fixture
def setup(monkeypatch):
    nx = ModuleType("NXOpen")
    nx.Session = NS(MarkVisibility=NS(Visible=1))
    monkeypatch.setitem(sys.modules, "NXOpen", nx)
    second = object()
    state = {"value": 0.5, "unit": second, "mode": 0}
    initial = dict(state)
    writes = []

    def set_value(key, value, unit):
        writes.append(key)
        state.update(value=value, unit=unit)

    table = NS(
        GetIntegerPropertyValue=lambda _: state["mode"],
        GetBaseScalarWithDataPropertyValue=lambda _: (state["value"], state["unit"]),
        SetBaseScalarWithDataPropertyValue=set_value,
    )
    step = NS(PropertyTable=NS(GetIntegerPropertyValue=lambda _: 0))
    sol = NS(
        SolverType="NX MULTIPHYSICS",
        AnalysisType="Flow",
        StepCount=1,
        GetStepByIndex=lambda _: step,
        PropertyTable=NS(GetNamedPropertyTablePropertyValue=lambda _: NS(PropertyTable=table)),
    )
    sim = NS(Simulation=NS(ActiveSolution=sol), UnitCollection=NS(FindObject=lambda _: second))
    session = NS(
        Parts=NS(BaseWork=sim),
        SetUndoMark=lambda *_: 1,
        UndoToMark=lambda *_: state.update(initial),
        DeleteUndoMark=lambda *_: None,
        UpdateManager=NS(DoUpdate=lambda _: 0),
    )
    return session, sim, table, state, writes, step


def test_change_and_idempotence(setup):
    session, sim, _, state, writes, _ = setup
    r = configure_physical_step(session, sim, time_step_s=0.05)
    assert r["before_s"] == 0.5 and r["actual_s"] == 0.05
    assert writes == ["Time Step"] and state["mode"] == 0
    assert not configure_physical_step(session, sim, time_step_s=0.05)["changed"]
    assert writes == ["Time Step"]


@pytest.mark.parametrize("value", [True, 0, -1, float("nan"), float("inf"), "0.05"])
def test_invalid_values_do_not_write(setup, value):
    session, sim, _, _, writes, _ = setup
    with pytest.raises(NXToolError):
        configure_physical_step(session, sim, time_step_s=value)
    assert not writes


@pytest.mark.parametrize("kind", ["local", "unit", "transient", "inactive", "steps"])
def test_invalid_context_does_not_write(setup, kind):
    session, sim, _, state, writes, step = setup
    if kind == "local":
        state["mode"] = 1
    elif kind == "unit":
        state["unit"] = object()
    elif kind == "transient":
        step.PropertyTable.GetIntegerPropertyValue = lambda _: 1
    elif kind == "inactive":
        session.Parts.BaseWork = None
    else:
        sim.Simulation.ActiveSolution.StepCount = 2
    with pytest.raises(NXToolError):
        configure_physical_step(session, sim, time_step_s=0.05)
    assert not writes


@pytest.mark.parametrize("kind", ["update", "readback", "rollback"])
def test_failure_is_rolled_back_or_partial(setup, kind):
    session, sim, table, state, _, _ = setup
    if kind == "readback":
        table.SetBaseScalarWithDataPropertyValue = lambda *_: None
    else:
        session.UpdateManager.DoUpdate = lambda _: 1
    if kind == "rollback":
        session.UndoToMark = lambda *_: None
    with pytest.raises(NXToolError) as error:
        configure_physical_step(session, sim, time_step_s=0.05)
    if kind == "rollback":
        assert error.value.code == "NX_SIM_ROLLBACK_FAILED"
    else:
        assert state["value"] == 0.5


def test_public_adapter_rejects_live_solver_before_resolving(setup, monkeypatch):
    from nx_mcp.simcenter import solver_guard
    from nx_mcp.simcenter.native import SimcenterMixin

    cae = ModuleType("NXOpen.CAE")
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)
    monkeypatch.setattr(sys.modules["NXOpen"], "CAE", cae, raising=False)

    def busy():
        raise NXToolError("NX_SIM_SOLVER_BUSY", "busy")

    monkeypatch.setattr(solver_guard, "require_solver_idle", busy)
    with pytest.raises(NXToolError) as error:
        SimcenterMixin._sim_flow_relaxation_step(NS(), "document", 0.05)
    assert error.value.code == "NX_SIM_SOLVER_BUSY"

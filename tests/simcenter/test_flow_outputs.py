import sys
from types import ModuleType
from types import SimpleNamespace as NS

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.flow_outputs import configure_outputs


@pytest.fixture
def setup(monkeypatch):
    nx = ModuleType("NXOpen")
    nx.Session = NS(MarkVisibility=NS(Visible=1))
    monkeypatch.setitem(sys.modules, "NXOpen", nx)
    state = {"Mass Fluxes": False, "Surface Pressure": False, "Y+": False, "Velocities": True}
    initial = dict(state)
    writes = []

    def write(name, value):
        writes.append(name)
        state[name] = value

    table = NS(
        GetBooleanPropertyValue=lambda name: state[name],
        SetBooleanPropertyValue=write,
        GetIntegerPropertyValue=lambda _: 0,
    )
    step = NS(PropertyTable=NS(GetNamedPropertyTablePropertyValue=lambda _: None))
    sol = NS(
        SolverType="NX MULTIPHYSICS",
        AnalysisType="Coupled Thermal-Flow",
        StepCount=1,
        GetStepByIndex=lambda _: step,
        PropertyTable=NS(GetNamedPropertyTablePropertyValue=lambda _: NS(PropertyTable=table)),
    )
    sim = NS(Simulation=NS(ActiveSolution=sol))
    session = NS(
        Parts=NS(BaseWork=sim),
        SetUndoMark=lambda *_: 1,
        UndoToMark=lambda *_: (state.clear(), state.update(initial)),
        DeleteUndoMark=lambda *_: None,
        UpdateManager=NS(DoUpdate=lambda _: 0),
    )
    return session, sim, table, state, writes, step


def change(setup, **kw):
    flags = {"mass_fluxes": True, "surface_pressure": True, "y_plus": True}
    flags.update(kw)
    return configure_outputs(setup[0], setup[1], **flags)


def test_enables_only_requested_outputs_and_noop(setup):
    result = change(setup)
    assert setup[4] == ["Mass Fluxes", "Surface Pressure", "Y+"]
    assert setup[3]["Velocities"] is True
    assert all(result["actual"].values())
    assert not result["existing_results_regenerated"]
    assert not result["flux_conservation_verified"]
    assert not change(setup)["changed"]
    assert len(setup[4]) == 3


@pytest.mark.parametrize("bad", [None, 0, 1, "true", 0.5])
def test_requires_actual_booleans_without_writes(setup, bad):
    with pytest.raises(NXToolError):
        change(setup, mass_fluxes=bad)
    assert not setup[4]


@pytest.mark.parametrize(
    "kind",
    [
        "override",
        "selected_entities",
        "inactive",
        "missing",
        "steps",
        "wrong_type",
        "native_nonbool",
    ],
)
def test_unsupported_context_rejected_before_mutation(setup, kind):
    session, sim, table, state, writes, step = setup
    if kind == "override":
        step.PropertyTable.GetNamedPropertyTablePropertyValue = lambda _: object()
    elif kind == "selected_entities":
        table.GetIntegerPropertyValue = lambda _: 1
    elif kind == "inactive":
        session.Parts.BaseWork = None
    elif kind == "missing":
        sim.Simulation.ActiveSolution.PropertyTable.GetNamedPropertyTablePropertyValue = lambda _: (
            None
        )
    elif kind == "steps":
        sim.Simulation.ActiveSolution.StepCount = 2
    elif kind == "wrong_type":
        sim.Simulation.ActiveSolution.AnalysisType = "Flow"
    else:
        state["Y+"] = 0
    with pytest.raises(NXToolError):
        change(setup)
    assert not writes


@pytest.mark.parametrize("kind", ["update", "second_write", "readback", "rollback"])
def test_atomic_failure_and_rollback(setup, kind):
    session, _, table, state, _, _ = setup
    before = dict(state)
    if kind == "readback":
        table.SetBooleanPropertyValue = lambda *_: None
    elif kind == "second_write":
        write = table.SetBooleanPropertyValue

        def fail(name, value):
            if name == "Surface Pressure":
                raise RuntimeError("native write failed")
            write(name, value)

        table.SetBooleanPropertyValue = fail
    else:
        session.UpdateManager.DoUpdate = lambda _: 1
    if kind == "rollback":
        session.UndoToMark = lambda *_: None
    with pytest.raises((NXToolError, RuntimeError)) as error:
        change(setup)
    if kind == "rollback":
        assert error.value.code == "NX_SIM_ROLLBACK_FAILED"
    else:
        assert state == before


def test_adapter_excludes_live_solver_before_resolution(setup, monkeypatch):
    from nx_mcp.simcenter import solver_guard
    from nx_mcp.simcenter.native import SimcenterMixin

    cae = ModuleType("NXOpen.CAE")
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)
    monkeypatch.setattr(sys.modules["NXOpen"], "CAE", cae, raising=False)

    def busy():
        raise NXToolError("NX_SIM_SOLVER_BUSY", "busy")

    monkeypatch.setattr(solver_guard, "require_solver_idle", busy)
    with pytest.raises(NXToolError) as error:
        SimcenterMixin._sim_flow_diagnostic_outputs(NS(), "document", True, True, True)
    assert error.value.code == "NX_SIM_SOLVER_BUSY"

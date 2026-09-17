import sys
from types import ModuleType
from types import SimpleNamespace as NS

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.flow_relaxation import FACTORS, configure_relaxation


@pytest.fixture
def setup(monkeypatch):
    nx = ModuleType("NXOpen")
    nx.Session = NS(MarkVisibility=NS(Visible=1))
    monkeypatch.setitem(sys.modules, "NXOpen", nx)
    state = {
        name: (value, None) for name, value in zip(FACTORS.values(), (0.75, 0.75, 0.9), strict=True)
    }
    initial = dict(state)
    writes = []

    def write(name, value, unit):
        writes.append(name)
        state[name] = (value, unit)

    table = NS(
        GetBaseScalarWithDataPropertyValue=lambda name: state[name],
        SetBaseScalarWithDataPropertyValue=write,
    )
    step = NS(PropertyTable=NS(GetIntegerPropertyValue=lambda _: 0))
    sol = NS(
        SolverType="NX MULTIPHYSICS",
        AnalysisType="Flow",
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
    values = {"global_factor": 0.3, "mass_factor": 0.2, "fluids_factor": 0.2}
    values.update(kw)
    return configure_relaxation(setup[0], setup[1], **values)


def test_native_property_mapping_and_noop(setup):
    report = change(setup)
    assert setup[4] == [
        "Global Relaxation Factor",
        "Mass Relaxation Factor",
        "Fluids Relaxation Factor",
    ]
    assert report["actual"] == {"global_factor": 0.3, "mass_factor": 0.2, "fluids_factor": 0.2}
    assert report["native_acceptance"] == "pending"
    assert not report["solver_launched"] and not report["saved"]
    assert not change(setup)["changed"]
    assert len(setup[4]) == 3


@pytest.mark.parametrize("bad", [True, 0, -1, 1.01, float("nan"), float("inf"), "0.3"])
def test_invalid_request_never_mutates(setup, bad):
    with pytest.raises(NXToolError):
        change(setup, mass_factor=bad)
    assert not setup[4]


@pytest.mark.parametrize(
    "kind", ["unit", "range", "nonfinite", "inactive", "transient", "steps", "missing"]
)
def test_context_preflight_never_mutates(setup, kind):
    session, sim, _, state, writes, step = setup
    if kind in {"unit", "range", "nonfinite"}:
        state["Mass Relaxation Factor"] = (
            (0.75, object()) if kind == "unit" else (0 if kind == "range" else float("nan"), None)
        )
    elif kind == "inactive":
        session.Parts.BaseWork = None
    elif kind == "transient":
        step.PropertyTable.GetIntegerPropertyValue = lambda _: 1
    elif kind == "steps":
        sim.Simulation.ActiveSolution.StepCount = 2
    else:
        sim.Simulation.ActiveSolution.PropertyTable.GetNamedPropertyTablePropertyValue = lambda _: (
            None
        )
    with pytest.raises(NXToolError):
        change(setup)
    assert not writes


@pytest.mark.parametrize("kind", ["update", "readback", "second_write", "rollback"])
def test_transaction_failure_restores_all_factors_or_reports_partial(setup, kind):
    session, _, table, state, _, _ = setup
    before = dict(state)
    if kind == "readback":
        table.SetBaseScalarWithDataPropertyValue = lambda *_: None
    elif kind == "second_write":
        write = table.SetBaseScalarWithDataPropertyValue

        def fail(name, value, unit):
            if name == "Mass Relaxation Factor":
                raise RuntimeError("native write failed")
            write(name, value, unit)

        table.SetBaseScalarWithDataPropertyValue = fail
    else:
        session.UpdateManager.DoUpdate = lambda _: 1
    if kind == "rollback":
        session.UndoToMark = lambda *_: None
    with pytest.raises((NXToolError, RuntimeError)) as error:
        change(setup)
    if kind == "rollback":
        assert error.value.code == "NX_SIM_ROLLBACK_FAILED"
        assert error.value.details["mutation_outcome"] == "partial"
    else:
        assert state == before


def test_adapter_blocks_live_solver_before_document_resolution(setup, monkeypatch):
    from nx_mcp.simcenter import solver_guard
    from nx_mcp.simcenter.native import SimcenterMixin

    cae = ModuleType("NXOpen.CAE")
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)
    monkeypatch.setattr(sys.modules["NXOpen"], "CAE", cae, raising=False)

    def busy():
        raise NXToolError("NX_SIM_SOLVER_BUSY", "busy")

    monkeypatch.setattr(solver_guard, "require_solver_idle", busy)
    with pytest.raises(NXToolError) as error:
        SimcenterMixin._sim_flow_relaxation(NS(), "document", 0.3, 0.2, 0.2)
    assert error.value.code == "NX_SIM_SOLVER_BUSY"


def test_optional_fan_damping_preserves_other_factors(setup):
    name = "Fan Curves (I/O/Internal Fans) Relaxation Factor"
    setup[3][name] = (1.0, None)
    report = change(
        setup, global_factor=0.75, mass_factor=0.75, fluids_factor=0.9, fan_curve_factor=0.1
    )
    assert setup[4] == [name]
    assert report["before"]["fan_curve_factor"] == 1.0
    assert report["actual"]["fan_curve_factor"] == 0.1
    assert setup[3][name] == (0.1, None)


@pytest.mark.parametrize("bad", [True, 0, -1, 1.01, float("nan"), float("inf"), "0.1"])
def test_invalid_optional_fan_damping_never_mutates(setup, bad):
    with pytest.raises(NXToolError):
        change(setup, fan_curve_factor=bad)
    assert not setup[4]


def test_omitted_fan_damping_is_untouched(setup):
    name = "Fan Curves (I/O/Internal Fans) Relaxation Factor"
    setup[3][name] = (0.123, None)
    change(setup)
    assert setup[3][name] == (0.123, None)
    assert name not in setup[4]


def test_fan_damping_readback_failure_rolls_back(setup):
    session, sim, table, state, _, _ = setup
    name = "Fan Curves (I/O/Internal Fans) Relaxation Factor"
    state[name] = (1.0, None)
    before = dict(state)
    session.UndoToMark = lambda *_: (state.clear(), state.update(before))
    table.SetBaseScalarWithDataPropertyValue = lambda *_: None
    with pytest.raises(NXToolError) as error:
        change(setup, fan_curve_factor=0.1)
    assert error.value.code == "NX_SIM_READBACK_MISMATCH"
    assert state == before

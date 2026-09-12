import sys
from types import ModuleType
from types import SimpleNamespace as NS

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.flow_controls import configure_convergence


@pytest.fixture
def native(monkeypatch):
    nx = ModuleType("NXOpen")
    nx.Session = NS(MarkVisibility=NS(Visible=1))
    monkeypatch.setitem(sys.modules, "NXOpen", nx)
    data = {
        "Maximum Residuals": 0.0002,
        "Global Flow Imbalance Fraction": 0.02,
        "Global Flow Imbalance Fraction Option": False,
        "3D Flow Steady State - Iteration Limit": 1000,
        "Convergence Criteria": 1,
        "Global Heat Imbalance Fraction": 0.02,
        "Global Heat Imbalance Fraction Option": False,
    }
    before = dict(data)
    table = NS(
        GetIntegerPropertyValue=lambda k: data[k],
        GetBooleanPropertyValue=lambda k: data[k],
        GetBaseScalarWithDataPropertyValue=lambda k: (data[k], None),
        SetIntegerPropertyValue=lambda k, v: data.update({k: v}),
        SetBooleanPropertyValue=lambda k, v: data.update({k: v}),
        SetBaseScalarWithDataPropertyValue=lambda k, v, u: data.update({k: v}),
    )
    sol = NS(
        SolverType="NX MULTIPHYSICS",
        AnalysisType="Flow",
        PropertyTable=NS(GetNamedPropertyTablePropertyValue=lambda _: NS(PropertyTable=table)),
    )
    sim = NS(Simulation=NS(ActiveSolution=sol))
    events = []

    def undo(*_):
        data.update(before)
        events.append("undo")

    session = NS(
        Parts=NS(BaseWork=sim),
        SetUndoMark=lambda *_: events.append("mark") or 1,
        UndoToMark=undo,
        DeleteUndoMark=lambda *_: None,
    )
    return session, sim, table, data, events


@pytest.mark.parametrize("value", [True, 0, -1, 1, float("nan"), float("inf")])
def test_invalid_fraction_does_not_mutate(native, value):
    session, sim, _, _, events = native
    with pytest.raises(NXToolError, match="finite fraction") as exc:
        configure_convergence(
            session, sim, residual=value, flow_imbalance_fraction=0.001, iteration_limit=1000
        )
    assert events == []
    assert exc.value.details["mutation_outcome"] == "not_started"


def test_partial_set_failure_restores_all_properties(native):
    session, sim, table, data, events = native
    before = dict(data)

    def fail(*_):
        raise RuntimeError("native setter failed")

    table.SetBooleanPropertyValue = fail
    with pytest.raises(RuntimeError, match="native setter"):
        configure_convergence(
            session, sim, residual=1e-6, flow_imbalance_fraction=0.001, iteration_limit=1000
        )
    assert data == before
    assert events == ["mark", "undo"]


def test_failed_rollback_is_partial(native):
    session, sim, table, _, _ = native

    def fail(*_):
        raise RuntimeError("native failure")

    table.SetBooleanPropertyValue = fail
    session.UndoToMark = fail
    with pytest.raises(NXToolError) as exc:
        configure_convergence(
            session, sim, residual=1e-6, flow_imbalance_fraction=0.001, iteration_limit=1000
        )
    assert exc.value.details["mutation_outcome"] == "partial"


@pytest.mark.parametrize("analysis", ["Flow", "Coupled Thermal-Flow"])
def test_supported_analysis_controls_commit_and_repeat_without_mutation(native, analysis):
    session, sim, table, data, events = native
    sim.Simulation.ActiveSolution.AnalysisType = analysis
    args = {"residual": 1e-6, "flow_imbalance_fraction": 0.001, "iteration_limit": 1000}
    result = configure_convergence(session, sim, **args)
    assert result["actual"]["flow_imbalance_enabled"]
    assert result["actual"]["residual"] == 1e-6
    count = len(events)
    assert not configure_convergence(session, sim, **args)["changed"]
    assert len(events) == count


@pytest.mark.parametrize("heat", [True, False, 0, -0.1, 1, float("nan"), float("inf"), "0.001"])
def test_invalid_heat_fraction_rejects_without_mutation(native, heat):
    session, sim, _, _, events = native
    with pytest.raises(NXToolError, match="finite fraction"):
        configure_convergence(
            session,
            sim,
            residual=1e-5,
            flow_imbalance_fraction=0.001,
            iteration_limit=1000,
            heat_imbalance_fraction=heat,
        )
    assert not events


def test_heat_control_is_opt_in_and_repeats_without_mutation(native):
    session, sim, _, data, events = native
    args = {"residual": 1e-5, "flow_imbalance_fraction": 0.001, "iteration_limit": 1000}
    configure_convergence(session, sim, **args)
    assert data["Global Heat Imbalance Fraction"] == 0.02
    assert not data["Global Heat Imbalance Fraction Option"]
    result = configure_convergence(session, sim, **args, heat_imbalance_fraction=0.001)
    assert result["actual"]["heat_imbalance_fraction"] == 0.001
    assert result["actual"]["heat_imbalance_enabled"] is True
    count = len(events)
    assert not configure_convergence(session, sim, **args, heat_imbalance_fraction=0.001)["changed"]
    assert len(events) == count


@pytest.mark.parametrize("failure", ["heat_enable", "readback", "unit"])
def test_heat_failure_preserves_original_controls(native, failure):
    session, sim, table, data, events = native
    before = dict(data)
    if failure == "unit":
        table.GetBaseScalarWithDataPropertyValue = lambda k: (
            data[k],
            "W" if k == "Global Heat Imbalance Fraction" else None,
        )
    elif failure == "readback":
        table.SetBaseScalarWithDataPropertyValue = lambda k, v, u: data.update(
            {k: 0.02 if k == "Global Heat Imbalance Fraction" else v}
        )
    else:

        def setter(k, v):
            if k == "Global Heat Imbalance Fraction Option":
                raise RuntimeError("heat enable failure")
            data[k] = v

        table.SetBooleanPropertyValue = setter
    with pytest.raises((NXToolError, RuntimeError)):
        configure_convergence(
            session,
            sim,
            residual=1e-5,
            flow_imbalance_fraction=0.001,
            iteration_limit=1000,
            heat_imbalance_fraction=0.001,
        )
    assert data == before
    assert events == ([] if failure == "unit" else ["mark", "undo"])


def test_convergence_adapter_rejects_busy_solver_before_resolving(native, monkeypatch):
    from nx_mcp.simcenter import solver_guard
    from nx_mcp.simcenter.native import SimcenterMixin

    cae = ModuleType("NXOpen.CAE")
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)
    monkeypatch.setattr(sys.modules["NXOpen"], "CAE", cae, raising=False)

    def busy():
        raise NXToolError("NX_SIM_SOLVER_BUSY", "busy")

    monkeypatch.setattr(solver_guard, "require_solver_idle", busy)
    with pytest.raises(NXToolError) as exc:
        SimcenterMixin._sim_flow_convergence(NS(), "document", 1e-5, 0.001, 1000, 0.001)
    assert exc.value.code == "NX_SIM_SOLVER_BUSY"

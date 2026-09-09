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
    args = dict(residual=1e-6, flow_imbalance_fraction=0.001, iteration_limit=1000)
    result = configure_convergence(session, sim, **args)
    assert result["actual"]["flow_imbalance_enabled"]
    assert result["actual"]["residual"] == 1e-6
    count = len(events)
    assert not configure_convergence(session, sim, **args)["changed"]
    assert len(events) == count

import sys
from types import ModuleType
from types import SimpleNamespace as NS

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.flow_model import MODELS, configure_model


@pytest.fixture
def setup(monkeypatch):
    nx = ModuleType("NXOpen")
    nx.Session = NS(MarkVisibility=NS(Visible=1))
    monkeypatch.setitem(sys.modules, "NXOpen", nx)
    values = {"Turbulence Model": 2, "Wall Treatment": 3}
    original = dict(values)
    calls = []
    table = NS(
        GetIntegerPropertyValue=lambda k: values[k],
        GetBooleanPropertyValue=lambda k: True,
        SetIntegerPropertyValue=lambda k, v: (calls.append(k), values.update({k: v})),
    )
    table.GetNamedPropertyTablePropertyValue = lambda _: NS(PropertyTable=table)
    sol = NS(SolverType="NX MULTIPHYSICS", AnalysisType="Coupled Thermal-Flow", PropertyTable=table)
    sim = NS(Simulation=NS(ActiveSolution=sol))
    session = NS(
        Parts=NS(BaseWork=sim),
        SetUndoMark=lambda *_: 1,
        UndoToMark=lambda *_: values.update(original),
        DeleteUndoMark=lambda *_: None,
        UpdateManager=NS(DoUpdate=lambda _: 0),
    )
    return session, sim, table, values, calls


@pytest.mark.parametrize("model", MODELS)
def test_model_change_preserves_wall_by_default_and_repeats_without_writes(setup, model):
    session, sim, _, values, calls = setup
    if model == "laminar":
        values["Wall Treatment"] = 0
    prior_wall = values["Wall Treatment"]
    result = configure_model(session, sim, model=model)
    assert result["actual"]["turbulence_model"] == MODELS[model]
    assert values["Wall Treatment"] == prior_wall
    assert "Wall Treatment" not in calls
    count = len(calls)
    assert not configure_model(session, sim, model=model)["changed"]
    assert len(calls) == count
    assert result["wall_overrides"] == "not_inspected"


def test_explicit_wall_choice_updates_both_selectors(setup):
    session, sim, _, values, _ = setup
    sim.Simulation.ActiveSolution.AnalysisType = "Flow"
    configure_model(session, sim, model="laminar", wall_treatment="no_slip")
    assert values == {"Turbulence Model": 0, "Wall Treatment": 0}


@pytest.mark.parametrize("failure", ["setter", "readback", "update", "rollback"])
def test_failed_change_rolls_back_or_reports_partial(setup, failure):
    session, sim, table, values, _ = setup
    old = dict(values)
    if failure == "setter":

        def setter(key, value):
            if key == "Wall Treatment":
                raise RuntimeError("setter failure")
            values[key] = value

        table.SetIntegerPropertyValue = setter
    elif failure == "readback":
        table.SetIntegerPropertyValue = lambda *_: None
    else:
        session.UpdateManager.DoUpdate = lambda _: 1
    if failure == "rollback":
        session.UndoToMark = lambda *_: None
    with pytest.raises((NXToolError, RuntimeError)) as exc:
        configure_model(session, sim, model="sst", wall_treatment="no_slip")
    if failure == "rollback":
        assert exc.value.code == "NX_SIM_ROLLBACK_FAILED"
        assert exc.value.details["mutation_outcome"] == "partial"
    else:
        assert values == old


@pytest.mark.parametrize(
    "failure", ["inactive", "wrong_solver", "missing_surface", "bad_model", "bad_wall"]
)
def test_preconditions_make_no_writes(setup, failure):
    session, sim, table, _, calls = setup
    args = {"model": "sst"}
    if failure == "inactive":
        session.Parts.BaseWork = None
    elif failure == "wrong_solver":
        sim.Simulation.ActiveSolution.SolverType = "OTHER"
    elif failure == "missing_surface":
        table.GetNamedPropertyTablePropertyValue = lambda _: None
    elif failure == "bad_model":
        args["model"] = "automatic"
    else:
        args["wall_treatment"] = "automatic"
    with pytest.raises(NXToolError):
        configure_model(session, sim, **args)
    assert not calls


def test_native_adapter_rejects_busy_solver_before_resolving_or_mutating(setup, monkeypatch):
    from nx_mcp.simcenter import solver_guard
    from nx_mcp.simcenter.native import SimcenterMixin

    cae = ModuleType("NXOpen.CAE")
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)
    monkeypatch.setattr(sys.modules["NXOpen"], "CAE", cae, raising=False)

    def busy(**kwargs):
        assert kwargs == {}
        raise NXToolError("NX_SIM_SOLVER_RUNNING", "busy")

    monkeypatch.setattr(solver_guard, "require_solver_idle", busy)
    with pytest.raises(NXToolError) as exc:
        SimcenterMixin._sim_flow_model(NS(), "document", "sst")
    assert exc.value.code == "NX_SIM_SOLVER_RUNNING"


def test_inactive_global_wall_edit_and_laminar_wall_function_reject(setup):
    session, sim, table, _, calls = setup
    with pytest.raises(NXToolError, match="Laminar flow requires"):
        configure_model(session, sim, model="laminar")
    table.GetBooleanPropertyValue = lambda _: False
    with pytest.raises(NXToolError, match="inactive"):
        configure_model(session, sim, model="sst", wall_treatment="no_slip")
    assert not calls
    result = configure_model(session, sim, model="mixing_length")
    assert result["global_wall_treatment_active"] is False

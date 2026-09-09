import sys
from types import ModuleType
from types import SimpleNamespace as NS

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter import steady_controls as controls


@pytest.mark.parametrize(
    "delta,limit,fraction",
    [
        (0, 100, None),
        (True, 100, None),
        (0.001, True, None),
        (0.001, 0, None),
        (0.001, 100, 2),
        (0.001, 100, float("nan")),
    ],
)
def test_invalid_controls(delta, limit, fraction):
    with pytest.raises(NXToolError):
        controls.validate(delta, limit, fraction)


def fixture(monkeypatch):
    delta = NS(Name="CelsiusDifference")
    values = {
        controls.MODE: 0,
        controls.CHANGE: (0.01, None),
        controls.LIMIT: 10000,
        controls.BALANCE: False,
        controls.OPTION: 1,
        controls.FRACTION: (0.01, None),
    }
    saved = dict(values)
    state = {"ignore_mode": False, "marks": 0}

    def integer(key, value):
        if not (key == controls.MODE and state["ignore_mode"]):
            values[key] = value

    table = NS(
        GetIntegerPropertyValue=lambda key: values[key],
        GetBooleanPropertyValue=lambda key: values[key],
        GetBaseScalarWithDataPropertyValue=lambda key: values[key],
        SetIntegerPropertyValue=integer,
        SetBooleanPropertyValue=lambda key, value: values.update({key: value}),
        SetBaseScalarWithDataPropertyValue=lambda key, value, unit: values.update(
            {key: (value, unit)}
        ),
    )
    sim = NS(UnitCollection=NS(FindObject=lambda name: delta))
    owner = NS(DescriptorType="Thermal Parameters", OwningPart=sim, PropertyTable=table)
    sim.Simulation = NS(
        ActiveSolution=NS(
            SolverType="NX MULTIPHYSICS",
            AnalysisType="Thermal",
            StepCount=1,
            GetStepByIndex=lambda i: NS(PropertyTable=NS(GetIntegerPropertyValue=lambda key: 0)),
            PropertyTable=NS(GetNamedPropertyTablePropertyValue=lambda key: owner),
        )
    )

    def mark(*args):
        state["marks"] += 1
        return 1

    session = NS(
        Parts=NS(BaseWork=sim),
        SetUndoMark=mark,
        UndoToMark=lambda *args: (values.clear(), values.update(saved)),
        DeleteUndoMark=lambda *args: None,
    )
    nx = ModuleType("NXOpen")
    nx.Session = NS(MarkVisibility=NS(Visible=1))
    monkeypatch.setitem(sys.modules, "NXOpen", nx)
    monkeypatch.setattr("nx_mcp.simcenter.solver_guard.require_solver_idle", lambda: None)
    return session, sim, values, saved, state


@pytest.mark.parametrize("fraction", [None, 0.001])
def test_selectors_units_and_optional_balance(monkeypatch, fraction):
    session, sim, values, saved, state = fixture(monkeypatch)
    r = controls.configure(session, sim, 0.001, 100, fraction)
    assert r["actual"]["mode"] == 1
    assert r["actual"]["temperature_unit"] == "CelsiusDifference"
    assert r["actual"]["relative_heat_balance_enabled"] == (fraction is not None)
    assert r["actual"]["heat_balance_option"] == (0 if fraction is not None else 1)
    assert r["actual"]["iteration_limit"] == 100


def test_ignored_mode_cannot_return_success_and_rolls_back(monkeypatch):
    session, sim, values, saved, state = fixture(monkeypatch)
    state["ignore_mode"] = True
    with pytest.raises(NXToolError) as caught:
        controls.configure(session, sim, 0.001, 100, 0.001)
    assert caught.value.details["mutation_outcome"] == "rolled_back"
    assert values == saved

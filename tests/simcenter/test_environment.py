import sys
from types import ModuleType
from types import SimpleNamespace as NS

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.coupled_setup import SOLUTION_UNITS
from nx_mcp.simcenter.environment import configure, validate


@pytest.fixture
def rig(monkeypatch):
    nx, cae = ModuleType("NXOpen"), ModuleType("NXOpen.CAE")

    class SimPart:
        pass

    cae.SimPart = SimPart
    nx.Session = NS(MarkVisibility=NS(Visible=1))
    monkeypatch.setitem(sys.modules, "NXOpen", nx)
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)
    monkeypatch.setattr("nx_mcp.simcenter.solver_guard.require_solver_idle", lambda: {})
    values = {
        "Ambient Pressure": 1,
        "Buoyancy": False,
        "Fluid Temperature": (20, "Celsius"),
        "Absolute Pressure": (101325, "PressurePascals"),
    }
    before = dict(values)
    props = NS(
        GetIntegerPropertyValue=lambda k: 6 if k == "Solver Type" else values[k],
        GetStringPropertyValue=lambda k: SOLUTION_UNITS[k],
        GetBooleanPropertyValue=lambda k: values[k],
        SetBooleanPropertyValue=lambda k, v: values.update({k: v}),
        SetIntegerPropertyValue=lambda k, v: values.update({k: v}),
        GetScalarWithDataPropertyValue=lambda k: (values[k][0], NS(Name=values[k][1])),
        GetScalarFieldWrapperPropertyValue=lambda k: NS(GetFieldScaleFactor=lambda: 1.0),
        SetScalarFieldWrapperPropertyValue=lambda k, v: values.update({k: v}),
    )
    sim = SimPart()
    sim.Simulation = NS(
        ActiveSolution=NS(
            SolverType="NX MULTIPHYSICS", AnalysisType="Coupled Thermal-Flow", PropertyTable=props
        )
    )

    class Expressions(list):
        def CreateSystemNumberExpression(self, v, u):
            self.append(NS(Tag=len(self) + 1))
            return float(v), u.Name

    sim.Expressions = Expressions()
    sim.UnitCollection = NS(FindObject=lambda n: NS(Name=n))
    sim.FieldManager = NS(CreateScalarFieldWrapperWithExpression=lambda e: e)

    def undo(*a):
        values.clear()
        values.update(before)
        sim.Expressions.clear()

    session = NS(
        Parts=NS(BaseWork=sim),
        SetUndoMark=lambda *a: 1,
        UndoToMark=undo,
        DeleteUndoMark=lambda *a: None,
    )
    return session, sim, props, values


@pytest.mark.parametrize("temperature", [25, 40])
def test_distinct_explicit_ambient_and_native_units(rig, temperature):
    session, sim, props, values = rig
    r = configure(session, sim, temperature, 101325, False)
    assert r["actual"]["values"]["Fluid Temperature"] == {
        "value": temperature,
        "unit": "Celsius",
        "scale": 1.0,
    }
    assert r["actual"]["ambient_pressure_selector"] == 0
    assert values["Absolute Pressure"] == (101325, "PressurePascals")


def test_ignored_temperature_write_rolls_back(rig):
    session, sim, props, values = rig
    write = props.SetScalarFieldWrapperPropertyValue
    props.SetScalarFieldWrapperPropertyValue = lambda k, v: (
        None if k == "Fluid Temperature" else write(k, v)
    )
    with pytest.raises(NXToolError) as caught:
        configure(session, sim, 40, 100000, True)
    assert caught.value.details["mutation_outcome"] == "rolled_back"
    assert values["Ambient Pressure"] == 1 and not sim.Expressions


@pytest.mark.parametrize("args", [(-273.15, 101325, False), (25, 0, False), (25, 101325, 1)])
def test_invalid_settings(args):
    with pytest.raises(NXToolError):
        validate(*args)

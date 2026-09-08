import sys
from types import ModuleType
from types import SimpleNamespace as NS

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.external_conditions import assign_external_temperature


@pytest.fixture
def native(monkeypatch):
    from nx_mcp.simcenter import solver_guard

    monkeypatch.setattr(solver_guard, "require_solver_idle", lambda: {})
    nx = ModuleType("NXOpen")
    nx.Session = NS(MarkVisibility=NS(Visible=1))
    monkeypatch.setitem(sys.modules, "NXOpen", nx)
    values = {}
    bindings = {}
    events = []
    props = NS(
        SetIntegerPropertyValue=lambda k, v: values.update({k: v}),
        GetIntegerPropertyValue=lambda k: values[k],
        SetScalarFieldWrapperPropertyValue=lambda k, v: values.update({k: v}),
        GetScalarWithDataPropertyValue=lambda k: (float(values[k]), NS(Name="Celsius")),
    )

    class Tables(list):
        def CreateModelingObjectPropertyTable(self, *args):
            t = NS(Tag=40, Name=args[3], PropertyTable=props)
            self.append(t)
            return t

    tables = Tables()
    sim = NS(
        Simulation=NS(
            ActiveSolution=NS(AnalysisType="Coupled Thermal-Flow", SolverType="NX MULTIPHYSICS")
        ),
        ModelingObjectPropertyTables=tables,
        Expressions=NS(CreateSystemNumberExpression=lambda v, u: v),
        UnitCollection=NS(FindObject=lambda u: u),
        FieldManager=NS(CreateScalarFieldWrapperWithExpression=lambda e: e),
    )
    boundary = NS(
        Tag=3,
        DescriptorName="Inlet",
        OwningPart=sim,
        PropertyTable=NS(
            GetNamedPropertyTablePropertyValue=lambda k: bindings.get(k),
            SetNamedPropertyTablePropertyValue=lambda k, v: bindings.update({k: v}),
        ),
    )
    sim.Simulation.SimulationObjects = [boundary]

    def undo(*args):
        tables.clear()
        bindings.clear()
        events.append("rollback")

    session = NS(
        Parts=NS(BaseWork=sim),
        SetUndoMark=lambda *a: 1,
        UndoToMark=undo,
        DeleteUndoMark=lambda *a: None,
    )
    return session, sim, boundary, props, events


def test_assignment_and_existing_assignment_protection(native):
    session, sim, boundary, props, events = native
    result = assign_external_temperature(session, sim, [boundary], "Air", 20)
    assert result["temperature_c"] == 20 and result["boundary_count"] == 1
    assert not result["global_ambient_changed"]
    with pytest.raises(NXToolError) as error:
        assign_external_temperature(session, sim, [boundary], "Other", 30)
    assert error.value.code == "NX_SIM_TABLE_EXISTS"
    assert len(sim.ModelingObjectPropertyTables) == 1


def test_readback_failure_restores_assignment(native):
    session, sim, boundary, props, events = native
    props.GetScalarWithDataPropertyValue = lambda k: (0, NS(Name="Celsius"))
    with pytest.raises(NXToolError) as error:
        assign_external_temperature(session, sim, [boundary], "Air", 20)
    assert error.value.details["mutation_outcome"] == "rolled_back"
    assert not sim.ModelingObjectPropertyTables and events == ["rollback"]
    assert boundary.PropertyTable.GetNamedPropertyTablePropertyValue("Inlet Conditions") is None


@pytest.mark.parametrize("temperature", [float("nan"), -273.15, True])
def test_invalid_temperature_never_creates(native, temperature):
    session, sim, boundary, props, events = native
    with pytest.raises(NXToolError):
        assign_external_temperature(session, sim, [boundary], "Air", temperature)
    assert not sim.ModelingObjectPropertyTables


def test_wrong_owner_rejected(native):
    session, sim, boundary, props, events = native
    boundary.OwningPart = None
    with pytest.raises(NXToolError) as error:
        assign_external_temperature(session, sim, [boundary], "Air", 20)
    assert error.value.code == "NX_SIM_SELECTION_OWNER"
    assert not sim.ModelingObjectPropertyTables

import sys
from types import ModuleType
from types import SimpleNamespace as NS

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter import flow


@pytest.fixture
def native(monkeypatch):
    nx, uf = ModuleType("NXOpen"), ModuleType("NXOpen.UF")
    nx.UF = uf
    nx.BasePart = NS(Units=NS(Millimeters=1))
    nx.Session = NS(MarkVisibility=NS(Visible=1))
    uf.UFSession = NS(
        GetUFSession=lambda: NS(
            Sf=NS(SolutionAskDescriptorNx=lambda _: 1),
            Sfl=NS(
                StepDescriptorAskNameNx=lambda _: "Step - Flow",
                SolutionAskNthAllowableStepDescriptorNx=lambda *a: 1,
            ),
        )
    )
    monkeypatch.setitem(sys.modules, "NXOpen", nx)
    monkeypatch.setitem(sys.modules, "NXOpen.UF", uf)
    step = NS(Name="Flow step", PropertyTable=object())
    sol = NS(
        SolverType="NX MULTIPHYSICS",
        AnalysisType="Flow",
        StepCount=0,
        Tag=1,
        AllowedStepTypeCount=1,
        GetStepByIndex=lambda _: step,
    )

    def create(*args):
        sol.StepCount = 1
        sol.ActiveStep = step
        return step

    sol.CreateStep = create
    sim = NS(Simulation=NS(ActiveSolution=sol), PartUnits=1)
    events = []

    def undo(*args):
        events.append("rollback")
        sol.StepCount = 0

    session = NS(
        Parts=NS(BaseWork=sim),
        SetUndoMark=lambda *a: events.append("mark") or 1,
        UndoToMark=undo,
        DeleteUndoMark=lambda *a: None,
    )
    return session, sim, events


def test_failed_readback_rolls_back_created_step(native, monkeypatch):
    session, sim, events = native

    def failed(*args):
        raise RuntimeError("native property read failed")

    monkeypatch.setattr("nx_mcp.simcenter.properties.read_properties", failed)
    with pytest.raises(RuntimeError, match="property read"):
        flow.create_initial_step(session, sim, "Flow step")
    assert sim.Simulation.ActiveSolution.StepCount == 0
    assert events == ["mark", "rollback"]


def test_existing_step_rejected_without_undo_or_mutation(native):
    session, sim, events = native
    sim.Simulation.ActiveSolution.StepCount = 1
    with pytest.raises(NXToolError) as error:
        flow.create_initial_step(session, sim, "Another step")
    assert error.value.code == "NX_SIM_STEP_EXISTS"
    assert events == []


def test_failed_recovery_is_reported_as_partial(native, monkeypatch):
    session, sim, _ = native

    def failed_read(*args):
        raise RuntimeError("readback failed")

    def failed_undo(*args):
        raise RuntimeError("native undo failed")

    monkeypatch.setattr("nx_mcp.simcenter.properties.read_properties", failed_read)
    session.UndoToMark = failed_undo
    with pytest.raises(NXToolError) as error:
        flow.create_initial_step(session, sim, "Flow step")
    assert error.value.code == "NX_SIM_ROLLBACK_FAILED"
    assert error.value.details["mutation_outcome"] == "partial"


def test_existing_parameter_table_is_not_replaced(native):
    session, sim, events = native
    sim.Simulation.ActiveSolution.PropertyTable = NS(
        GetNamedPropertyTablePropertyValue=lambda _: object()
    )
    with pytest.raises(NXToolError) as error:
        flow.attach_default_tables(session, sim, "Test")
    assert error.value.code == "NX_SIM_TABLE_EXISTS"
    assert events == []


def test_partial_table_creation_is_rolled_back(native, monkeypatch):
    session, sim, events = native
    values = {}

    class Tables(list):
        def CreateModelingObjectPropertyTable(self, descriptor, language, solver, name, label):
            if self:
                raise RuntimeError("second native table creation failed")
            table = NS(Name=name, DescriptorType=descriptor, PropertyTable=object())
            self.append(table)
            return table

    tables = Tables()
    sim.ModelingObjectPropertyTables = tables
    sim.Simulation.ActiveSolution.PropertyTable = NS(
        GetNamedPropertyTablePropertyValue=lambda key: values.get(key),
        SetNamedPropertyTablePropertyValue=lambda key, table: values.update({key: table}),
    )

    def undo(*args):
        tables.clear()
        values.clear()
        events.append("rollback")

    session.UndoToMark = undo
    monkeypatch.setattr("nx_mcp.simcenter.properties.read_properties", lambda *a: [])
    with pytest.raises(RuntimeError, match="second native table"):
        flow.attach_default_tables(session, sim, "Test")
    assert not tables and not values
    assert events == ["mark", "rollback"]


def test_coupled_steady_readback_and_failed_edit_restore(native):
    session, sim, events = native
    sol = sim.Simulation.ActiveSolution
    sol.AnalysisType = "Coupled Thermal-Flow"
    sol.CreateStep()
    from nx_mcp.simcenter.coupled_setup import SOLUTION_UNITS

    setup_values = dict.fromkeys(SOLUTION_UNITS, "")
    setup_values["Solver Type"] = 0
    sol.PropertyTable = NS(
        GetIntegerPropertyValue=lambda key: setup_values[key],
        SetIntegerPropertyValue=lambda key, value: setup_values.update({key: value}),
        GetStringPropertyValue=lambda key: setup_values[key],
        SetStringPropertyValue=lambda key, value: setup_values.update({key: value}),
    )
    session.UpdateManager = NS(DoUpdate=lambda mark: 0)
    values = {"value": 1}
    sol.ActiveStep.PropertyTable = NS(
        GetIntegerPropertyValue=lambda _: values["value"],
        SetIntegerPropertyValue=lambda _, value: values.update(value=value),
    )
    result = flow.configure_coupled_steady(session, sim, "unused")
    assert result["native_value"] == 0 and result["previous_native_value"] == 1
    assert result["solve_ready"] is False
    values["value"] = 1
    sol.ActiveStep.PropertyTable.SetIntegerPropertyValue = lambda *a: values.update(value=2)
    session.UndoToMark = lambda *a: values.update(value=1)
    with pytest.raises(NXToolError) as error:
        flow.configure_coupled_steady(session, sim, "unused")
    assert error.value.code == "NX_SIM_READBACK_MISMATCH"
    assert values["value"] == 1


def test_coupled_property_key_uses_documented_distinct_descriptor(native, monkeypatch):
    session, sim, events = native
    sol = sim.Simulation.ActiveSolution
    sol.AnalysisType = "Coupled Thermal-Flow"
    assigned = {}
    created = []

    class Tables(list):
        def CreateModelingObjectPropertyTable(self, descriptor, language, solver, name, label):
            created.append((descriptor, language, solver))
            table = NS(Name=name, DescriptorType=descriptor, PropertyTable=object())
            self.append(table)
            return table

    sim.ModelingObjectPropertyTables = Tables()
    sol.PropertyTable = NS(
        GetNamedPropertyTablePropertyValue=lambda key: assigned.get(key),
        SetNamedPropertyTablePropertyValue=lambda key, value: assigned.update({key: value}),
    )
    monkeypatch.setattr("nx_mcp.simcenter.properties.read_properties", lambda *a: [])
    result = flow.attach_default_tables(session, sim, "Coupled")
    assert result["unresolved_controls"] == []
    assert len(assigned) == 5
    assert (
        assigned["Coupled Solution Parameters"].DescriptorType
        == "Thermal-Flow Coupled Solution Parameters"
    )
    assert created[-1] == (
        "Thermal-Flow Coupled Solution Parameters",
        "NX MULTIPHYSICS - Coupled Thermal-Flow",
        "NX MULTIPHYSICS",
    )
    assert events == ["mark"]

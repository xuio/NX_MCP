import sys
from types import ModuleType
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.flow_boundaries import create, validate


@pytest.fixture
def rig(monkeypatch):
    nx, cae = ModuleType("NXOpen"), ModuleType("NXOpen.CAE")

    class SimPart:
        pass

    cae.SimPart, cae.SetObject = SimPart, NS
    cae.CaeSetObjectSubType = NS(NotSet=0)
    nx.Session = NS(MarkVisibility=NS(Visible=1))
    monkeypatch.setitem(sys.modules, "NXOpen", nx)
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)
    monkeypatch.setattr("nx_mcp.simcenter.solver_guard.require_solver_idle", lambda: {})
    monkeypatch.setattr("nx_mcp.simcenter.properties.read_properties", lambda p, n: [])
    sim, values, objects = SimPart(), {}, []
    targets = []
    props = NS(
        SetIntegerPropertyValue=lambda k, v: values.update({k: v}),
        GetIntegerPropertyValue=lambda k: values[k],
        SetScalarFieldWrapperPropertyValue=lambda k, v: values.update({k: v}),
        GetScalarWithDataPropertyValue=lambda k: (values[k].value, values[k].unit),
    )
    manager = NS(
        SetTargetSetMembers=lambda i, v: targets.extend(v),
        GetTargetSetMembers=lambda i: (None, targets),
    )

    def commit():
        obj = NS(
            Tag=100,
            Name="boundary",
            DescriptorName="Inlet",
            PropertyTable=props,
            TargetSetManager=manager,
        )
        objects.append(obj)
        return obj

    builder = NS(PropertyTable=props, TargetSetManager=manager, CommitAddBc=commit, Destroy=Mock())
    factory = Mock(return_value=builder)
    sim.Simulation = NS(
        SimulationObjects=objects,
        CreateBcBuilderForSimulationObjectDescriptor=factory,
        ActiveSolution=NS(
            SolverType="NX MULTIPHYSICS",
            AnalysisType="Coupled Thermal-Flow",
            GetBcs=lambda: objects,
        ),
    )

    class Expressions(list):
        def CreateSystemNumberExpression(self, value, unit):
            e = NS(Tag=200, value=float(value), unit=unit)
            self.append(e)
            return e

    sim.Expressions = Expressions()
    sim.UnitCollection = NS(FindObject=lambda n: NS(Name=n))
    sim.FieldManager = NS(CreateScalarFieldWrapperWithExpression=lambda e: e)

    def undo(*a):
        objects.clear()
        sim.Expressions.clear()

    session = NS(
        Parts=NS(BaseWork=sim),
        SetUndoMark=Mock(return_value=1),
        UndoToMark=Mock(side_effect=undo),
        DeleteUndoMark=Mock(),
    )
    face = NS(Tag=5, OwningPart=sim, IsOccurrence=True)
    return NS(
        sim=sim,
        session=session,
        face=face,
        props=props,
        objects=objects,
        factory=factory,
        values=values,
    )


@pytest.mark.parametrize("kind,value,unit", [("inlet", 1.5, "m/s"), ("opening", 101325, "Pa")])
def test_committed_units_targets_and_membership(rig, kind, value, unit):
    result = create(rig.session, rig.sim, [rig.face], kind, "boundary", value)
    assert result["value"] == value and result["units"] == unit
    assert result["targets"]["committed_face_tags"] == [5]
    assert result["solution_member"]
    assert rig.values["Alignment"] == 0
    if kind == "opening":
        assert rig.values["Pressure"] == 1 and rig.values["External Pressure Type"] == 0


def test_foreign_selection_is_preflight(rig):
    rig.face.OwningPart = object()
    with pytest.raises(NXToolError, match="SIM occurrence"):
        create(rig.session, rig.sim, [rig.face], "inlet", "boundary", 1)
    rig.factory.assert_not_called()
    rig.session.SetUndoMark.assert_not_called()


def test_committed_mismatch_rolls_back_objects_and_expressions(rig):
    rig.props.GetScalarWithDataPropertyValue = lambda k: (0, NS(Name="MeterPerSecond"))
    with pytest.raises(NXToolError) as caught:
        create(rig.session, rig.sim, [rig.face], "inlet", "boundary", 1)
    assert caught.value.details["mutation_outcome"] == "rolled_back"
    assert not rig.objects and not rig.sim.Expressions


def test_overlap_never_creates_second_boundary(rig):
    create(rig.session, rig.sim, [rig.face], "inlet", "boundary", 1)
    with pytest.raises(NXToolError) as caught:
        create(rig.session, rig.sim, [rig.face], "opening", "other", 101325)
    assert caught.value.code == "NX_SIM_SELECTION_OVERLAP"
    assert rig.factory.call_count == 1


@pytest.mark.parametrize("value", [True, 0, -1, float("inf"), float("nan")])
def test_invalid_scalar(value):
    with pytest.raises(NXToolError):
        validate("inlet", "a", value, "normal_to_face")


@pytest.mark.asyncio
async def test_public_authoring_schema_and_native_dispatch(tmp_path, monkeypatch):
    from nx_mcp.server import create_server
    from nx_mcp.simcenter.native import SimcenterMixin
    from nx_mcp.workspace import Workspace

    monkeypatch.setenv("NX_MCP_ENABLE_SIMCENTER", "1")
    server = create_server(NS(), Workspace(tmp_path), enable_experimental=True)
    tools = {t.name: t for t in await server.list_tools()}
    for name in ("nx_sim_inlet", "nx_sim_opening", "nx_sim_fluid_material"):
        assert name in tools
        assert "operation_id" in tools[name].inputSchema["properties"]
        assert hasattr(SimcenterMixin, "_" + name[3:])
    assert "pressure_pa" in tools["nx_sim_opening"].inputSchema["required"]
    assert "density_kg_m3" in tools["nx_sim_fluid_material"].inputSchema["required"]

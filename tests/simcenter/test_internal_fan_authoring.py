import sys
from types import ModuleType
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.internal_fan_authoring import create, validate


@pytest.fixture
def rig(monkeypatch):
    nx, cae = ModuleType("NXOpen"), ModuleType("NXOpen.CAE")

    class SimPart:
        pass

    cae.SimPart, cae.SetObject = SimPart, NS
    cae.CaeSetObjectSubType = NS(NotSet=0)

    def strict_xyz(x, y, z):
        if any(type(v) is not float for v in (x, y, z)):
            raise TypeError("NX point/vector coordinates require double")
        return NS(X=x, Y=y, Z=z)

    nx.Point3d = strict_xyz
    nx.Vector3d = nx.Point3d
    nx.SmartObject = NS(UpdateOption=NS(WithinModeling=0))
    nx.Session = NS(MarkVisibility=NS(Visible=1))
    monkeypatch.setitem(sys.modules, "NXOpen", nx)
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)
    monkeypatch.setattr("nx_mcp.simcenter.solver_guard.require_solver_idle", lambda: {})
    monkeypatch.setattr("nx_mcp.simcenter.properties.read_properties", lambda p, n: [])
    sim, values, objects = SimPart(), {}, []
    targets = []
    sim.IsModified = False

    class Directions(list):
        def CreateDirection(self, origin, vector, update):
            d = NS(Tag=300, Origin=origin, Vector=vector, OwningPart=sim)
            self.append(d)
            return d

    sim.Directions = Directions()
    props = NS(
        SetVectorPropertyValue=lambda k, v: values.update({k: v}),
        GetVectorPropertyValue=lambda k: values[k],
        SetBaseScalarWithDataPropertyValue=lambda k, v, u: values.update({k: (v, u)}),
        GetBaseScalarWithDataPropertyValue=lambda k: values[k],
        GetScalarFieldWrapperPropertyValue=lambda k: values[k],
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
            DescriptorName="Internal Fan",
            OwningPart=sim,
            PropertyTable=props,
            TargetSetManager=manager,
        )
        sim.IsModified = True
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
    sim.FieldManager = NS(
        Fields=[],
        CreateScalarFieldWrapperWithExpression=lambda e: e,
        CreateScalarFieldWrapperWithField=lambda t, s: NS(
            GetField=lambda: t, GetFieldScaleFactor=lambda: s
        ),
    )

    def undo(*a):
        sim.IsModified = False
        sim.Directions.clear()
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


@pytest.mark.parametrize("flow,heat,direction", [(1e-4, 1, [2, 0, 0]), (2e-4, 0, [0, 0, -3])])
def test_committed_si_direction_heat_and_membership(rig, flow, heat, direction):
    r = create(rig.session, rig.sim, [rig.face], "fan", direction, heat, flow)
    assert r["volume_flow_m3_s"] == flow and r["motor_heat_w"] == heat
    assert r["orientation_vector"] == ([1, 0, 0] if direction[0] else [0, 0, -1])
    assert r["targets"]["committed_face_tags"] == [5] and r["solution_member"]
    assert rig.values["Mode Option"] == 3 and rig.values["Controller Type"] == 0
    assert not r["numerical_acceptance"] and not r["export_semantics_verified"]


def test_curve_uses_internal_mode_four(rig, monkeypatch):
    table = NS(Tag=600)
    monkeypatch.setattr(
        "nx_mcp.simcenter.fan_field.inspect_fan_table",
        lambda sim, t: {"manifest": {"pressure_convention": "static"}},
    )
    r = create(rig.session, rig.sim, [rig.face], "fan", [1, 0, 0], 1, table=table)
    assert r["mode"] == "fan_curve" and rig.values["Mode Option"] == 4
    assert rig.values["Fan Curve"].GetField() is table


def test_foreign_face_rejected_before_mutation(rig):
    rig.face.OwningPart = object()
    with pytest.raises(NXToolError):
        create(rig.session, rig.sim, [rig.face], "fan", [1, 0, 0], 1, 1e-4)
    rig.factory.assert_not_called()
    rig.session.SetUndoMark.assert_not_called()


def test_overlap_rejected_before_second_commit(rig):
    create(rig.session, rig.sim, [rig.face], "fan", [1, 0, 0], 1, 1e-4)
    with pytest.raises(NXToolError) as caught:
        create(rig.session, rig.sim, [rig.face], "second", [1, 0, 0], 1, 1e-4)
    assert caught.value.code == "NX_SIM_SELECTION_OVERLAP" and rig.factory.call_count == 1


def test_readback_failure_restores_direction_expression_and_modified_state(rig):
    rig.props.GetScalarWithDataPropertyValue = lambda k: (0, NS(Name="CubicMeterPerSecond"))
    with pytest.raises(NXToolError) as caught:
        create(rig.session, rig.sim, [rig.face], "fan", [1, 0, 0], 1, 1e-4)
    assert caught.value.details["mutation_outcome"] == "rolled_back"
    assert (
        not rig.objects
        and not rig.sim.Expressions
        and not rig.sim.Directions
        and not rig.sim.IsModified
    )


def test_direction_leak_reports_partial(rig):
    undo = rig.session.UndoToMark.side_effect

    def leak(*args):
        undo(*args)
        rig.sim.Directions.append(NS(Tag=999))

    rig.session.UndoToMark.side_effect = leak
    rig.props.GetScalarWithDataPropertyValue = lambda k: (0, NS(Name="CubicMeterPerSecond"))
    with pytest.raises(NXToolError) as caught:
        create(rig.session, rig.sim, [rig.face], "fan", [1, 0, 0], 1, 1e-4)
    assert caught.value.code == "NX_SIM_RECOVERY_INCOMPLETE"
    assert caught.value.details["mutation_outcome"] == "partial"


@pytest.mark.parametrize(
    "direction,heat,flow,table",
    [
        ([0, 0, 0], 0, 1, None),
        ([True, 0, 0], 0, 1, None),
        ([float("nan"), 0, 0], 0, 1, None),
        ([1, 0, 0], -1, 1, None),
        ([1, 0, 0], True, 1, None),
        ([1, 0, 0], 0, 0, None),
        ([1, 0, 0], 0, None, None),
        ([1, 0, 0], 0, 1, object()),
    ],
)
def test_invalid_inputs(direction, heat, flow, table):
    with pytest.raises(NXToolError):
        validate("fan", direction, heat, flow, table)


@pytest.mark.asyncio
async def test_public_surface(tmp_path, monkeypatch):
    from nx_mcp.server import create_server
    from nx_mcp.simcenter.native import SimcenterMixin
    from nx_mcp.workspace import Workspace

    monkeypatch.setenv("NX_MCP_ENABLE_SIMCENTER", "1")
    server = create_server(NS(), Workspace(tmp_path), enable_experimental=True)
    tools = {t.name: t for t in await server.list_tools()}
    schema = tools["nx_sim_internal_fan"].inputSchema
    assert {"document", "faces", "name", "direction", "motor_heat_w"}.issubset(schema["required"])
    assert "operation_id" in schema["properties"] and hasattr(SimcenterMixin, "_sim_internal_fan")

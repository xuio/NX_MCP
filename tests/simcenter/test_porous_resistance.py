import sys
from types import ModuleType
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.porous_resistance import DESCRIPTOR, create, validate


def test_si_conversion_is_directional_and_preserves_zero_inertia():
    k, c = validate("test", [1e-8, 2e-9, 3e-10], [10, 0, 30], True)
    assert k == pytest.approx([0.01, 0.002, 0.0003])
    assert c == pytest.approx([0.01, 0, 0.03])


@pytest.mark.parametrize(
    "values",
    [
        [True, 1, 1],
        [0, 1, 1],
        [-1, 1, 1],
        [float("nan"), 1, 1],
        [float("inf"), 1, 1],
        [1e308, 1, 1],
        [1, 2],
    ],
)
def test_invalid_permeability(values):
    with pytest.raises(NXToolError):
        validate("test", values, [0, 0, 0], True)


@pytest.fixture
def rig(monkeypatch):
    nx, cae = ModuleType("NXOpen"), ModuleType("NXOpen.CAE")
    cae.SimPart = type("SimPart", (), {})
    cae.SetObject = lambda: NS()
    cae.CaeSetObjectSubType = NS(NotSet=0)
    nx.Session = NS(MarkVisibility=NS(Visible=1))
    nx.BasePart = NS(Units=NS(Millimeters=0))
    nx.Point3d = nx.Vector3d = lambda *v: NS(X=v[0], Y=v[1], Z=v[2])
    nx.CAE = cae
    monkeypatch.setitem(sys.modules, "NXOpen", nx)
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)
    monkeypatch.setattr("nx_mcp.simcenter.solver_guard.require_solver_idle", lambda: {"idle": True})
    sim = cae.SimPart()
    sim.PartUnits = 0
    sim.Expressions, sim.FieldManager, sim.IsModified = [], NS(Fields=[]), False

    class Frames(list):
        def CreateCoordinateSystem(self, origin, x, y):
            f = NS(
                Tag=9,
                Origin=origin,
                Orientation=NS(
                    Element=NS(Xx=x.X, Xy=x.Y, Xz=x.Z, Yx=y.X, Yy=y.Y, Yz=y.Z, Zx=0, Zy=0, Zz=1)
                ),
            )
            self.append(f)
            return f

    sim.CoordinateSystems = Frames()
    sim.UnitCollection = NS(FindObject=lambda name: NS(Name=name))
    data = {}
    props = NS(
        SetCoordinateSystemPropertyValue=lambda k, v: data.update({k: v}),
        GetCoordinateSystemPropertyValue=lambda k: data[k],
        SetBooleanPropertyValue=lambda k, v: data.update({k: v}),
        GetBooleanPropertyValue=lambda k: data[k],
        SetBaseScalarWithDataPropertyValue=lambda k, v, u: data.update({k: (v, u)}),
        GetBaseScalarWithDataPropertyValue=lambda k: data[k],
    )
    selected = []
    targets = NS(
        TargetSetCount=1,
        SetTargetSetMembers=lambda i, m: selected.extend(m),
        GetTargetSetMembers=lambda i: (None, selected),
    )
    bcs = []
    boundary = NS(
        Tag=17,
        Name="test",
        DescriptorName=DESCRIPTOR,
        OwningPart=sim,
        PropertyTable=props,
        TargetSetManager=targets,
    )

    def commit():
        bcs.append(boundary)
        sim.IsModified = True
        return boundary

    builder = NS(PropertyTable=props, TargetSetManager=targets, CommitAddBc=commit, Destroy=Mock())
    sim.Simulation = NS(
        SimulationObjects=bcs,
        ActiveSolution=NS(
            SolverType="NX MULTIPHYSICS", AnalysisType="Coupled Thermal-Flow", GetBcs=lambda: bcs
        ),
        CreateBcBuilderForSimulationObjectDescriptor=Mock(return_value=builder),
    )

    def undo(*args):
        bcs.clear()
        sim.CoordinateSystems.clear()
        sim.IsModified = False

    session = NS(
        Parts=NS(BaseWork=sim),
        SetUndoMark=Mock(return_value=42),
        UndoToMark=Mock(side_effect=undo),
        DeleteUndoMark=Mock(),
    )
    body = NS(Tag=31, OwningPart=sim, IsOccurrence=True)
    return session, sim, body, builder, props, data


def run(rig):
    session, sim, body, *_ = rig
    return create(session, sim, [body], "test", [1e-8, 2e-9, 3e-10], [10, 0, 30], True)


def test_commit_checks_frame_targets_units_and_membership(rig):
    result = run(rig)
    assert result["target_count"] == 1
    assert result["native_coefficients"]["Y Permeability Value"]["value"] == pytest.approx(0.002)
    assert result["native_coefficients"]["Z Loss Coefficient per Length"]["value"] == pytest.approx(
        0.03
    )
    assert not result["saved"] and not result["numerical_acceptance"]
    rig[0].UndoToMark.assert_not_called()


def test_bad_unit_after_commit_rolls_back_object_and_frame(rig):
    session, sim, body, builder, props, data = rig
    props.GetBaseScalarWithDataPropertyValue = lambda k: (data[k][0], NS(Name="Meter"))
    with pytest.raises(NXToolError) as e:
        run(rig)
    assert e.value.details["mutation_outcome"] == "rolled_back"
    assert not sim.CoordinateSystems and not sim.Simulation.SimulationObjects and not sim.IsModified


def test_failed_undo_reports_partial(rig):
    session, sim, body, builder, props, data = rig
    builder.CommitAddBc = Mock(side_effect=RuntimeError("native failure"))
    session.UndoToMark.side_effect = RuntimeError("undo failure")
    with pytest.raises(NXToolError) as e:
        run(rig)
    assert e.value.details["mutation_outcome"] == "partial"


def test_existing_blockage_rejected_before_mutation(rig):
    session, sim, body, *_ = rig
    sim.Simulation.SimulationObjects.append(
        NS(
            Name="existing",
            DescriptorName=DESCRIPTOR,
            TargetSetManager=NS(
                TargetSetCount=1, GetTargetSetMembers=lambda i: (None, [NS(Obj=body)])
            ),
        )
    )
    with pytest.raises(NXToolError) as e:
        run(rig)
    assert e.value.code == "NX_SIM_SELECTION_OVERLAP"
    session.SetUndoMark.assert_not_called()


def test_running_solver_rejected_before_mutation(rig, monkeypatch):
    def busy():
        raise NXToolError("NX_SIM_SOLVER_BUSY", "busy")

    monkeypatch.setattr("nx_mcp.simcenter.solver_guard.require_solver_idle", busy)
    with pytest.raises(NXToolError):
        run(rig)
    rig[0].SetUndoMark.assert_not_called()

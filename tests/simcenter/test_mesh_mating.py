import sys
from types import ModuleType
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.mesh_mating import create


@pytest.fixture
def rig(monkeypatch):
    nx = ModuleType("NXOpen")
    cae = ModuleType("NXOpen.CAE")
    nx.CAE = cae
    monkeypatch.setitem(sys.modules, "NXOpen", nx)
    cae.FemPart = type("FemPart", (), {})
    cae.SimPart = type("SimPart", (), {})
    cae.MMCCreateBuilder = NS(
        Types=NS(Manual=1),
        MeshMatingType=NS(GlueCoincident=2),
        FaceSearchType=NS(IdenticalPairsOnly=1),
    )
    monkeypatch.setitem(sys.modules, "NXOpen.CAE", cae)
    monkeypatch.setattr("nx_mcp.simcenter.solver_guard.require_solver_idle", lambda: None)
    fem = cae.FemPart()
    fem.PartUnits = 1
    fem.FullPath = "coupon.fem"
    fem.Expressions = []
    source, target = NS(Tag=10, OwningPart=fem), NS(Tag=20, OwningPart=fem)
    rows = [
        {"face": f, "body": NS(Tag=i), "bounds": {"minimum": [20, 0, 0], "maximum": [20, 10, 10]}}
        for i, f in enumerate([source, target])
    ]
    monkeypatch.setattr("nx_mcp.simcenter.selections.face_inventory", lambda *_: {"rows": rows})

    class Expr:
        Units = NS(Name="MilliMeter")
        RightHandSide = "0.001"

        def GetFormula(self):
            return self.RightHandSide

    class Controls(list):
        corrupt_readback = False
        fail_commit = False

        def CreateMmcCreateBuilder(self, control):
            if control is not None:
                reader = NS(**vars(self.builder))
                if self.corrupt_readback:
                    reader.SourceFace = NS(Value=target)
                return reader
            builder = NS(
                SourceFace=NS(Value=None),
                TargetFace=NS(Value=None),
                DistTolerance=Expr(),
                SnapTolerance=Expr(),
                PrintLogOnInfoWindow=Mock(),
                Destroy=Mock(),
            )
            self.builder = builder

            def commit():
                control = NS(Tag=50)
                self.append(control)
                if self.fail_commit:
                    raise RuntimeError("native failure after partial creation")
                return [control]

            builder.CommitMmcs = commit
            return builder

    controls = Controls()
    fem.BaseFEModel = NS(MeshControls=controls, MeshManager=NS(GetMeshes=Mock(return_value=[])))

    class Parts(list):
        BaseWork = fem

    parts = Parts([fem])
    sim = cae.SimPart()
    sim.FemPart, sim.FullPath = fem, "coupon.sim"
    parts.append(sim)
    session = NS(
        Parts=parts,
        SetUndoMark=Mock(return_value=5),
        UndoToMark=Mock(side_effect=lambda *_: controls.clear()),
        DeleteUndoMark=Mock(),
    )
    executor = NS(
        session=session,
        nxopen=NS(BasePart=NS(Units=NS(Millimeters=1)), Session=NS(MarkVisibility=NS(Visible=1))),
        objects=NS(invalidate_part=Mock()),
        _part_id=lambda p: p.FullPath,
    )
    return executor, fem, source, target, controls, rows


def test_exact_requested_pair_and_tolerances_read_back_without_mesh_claim(rig):
    executor, fem, source, target, controls, _ = rig
    result = create(executor, fem, source, target, 0.002)
    assert result["kind"] == "glue_coincident"
    assert result["selected_face_tags"] == [10, 20]
    assert result["connectivity_verified"] is False
    assert result["mesh_generated"] is False
    assert controls.builder.DistTolerance.RightHandSide == "0.002"
    assert controls.builder.SnapTolerance.RightHandSide == "0.002"
    assert {c.args[0] for c in executor.objects.invalidate_part.call_args_list} == {
        "coupon.fem",
        "coupon.sim",
    }


@pytest.mark.parametrize("tolerance", [0, -0.1, 0.10001, float("inf"), float("nan"), True])
def test_invalid_tolerance_rejected_before_native_mutation(rig, tolerance):
    executor, fem, source, target, _, _ = rig
    with pytest.raises(NXToolError):
        create(executor, fem, source, target, tolerance)
    executor.session.SetUndoMark.assert_not_called()


def test_foreign_face_rejected_before_mutation(rig):
    executor, fem, source, target, _, _ = rig
    target.OwningPart = object()
    with pytest.raises(NXToolError):
        create(executor, fem, source, target, 0.001)
    executor.session.SetUndoMark.assert_not_called()


def test_noncoincident_bounds_rejected_before_mutation(rig):
    executor, fem, source, target, _, rows = rig
    rows[1]["bounds"]["minimum"][0] = 21
    with pytest.raises(NXToolError):
        create(executor, fem, source, target, 0.001)
    executor.session.SetUndoMark.assert_not_called()


def test_existing_mesh_rejected_without_edit(rig):
    executor, fem, source, target, _, _ = rig
    fem.BaseFEModel.MeshManager.GetMeshes.return_value = [NS(Tag=100)]
    with pytest.raises(NXToolError):
        create(executor, fem, source, target, 0.001)
    executor.session.SetUndoMark.assert_not_called()


@pytest.mark.parametrize("cause", ["corrupt_readback", "fail_commit"])
def test_partial_creation_or_wrong_selection_rolls_back_and_invalidates(rig, cause):
    executor, fem, source, target, controls, _ = rig
    setattr(controls, cause, True)
    with pytest.raises(NXToolError) as error:
        create(executor, fem, source, target, 0.001)
    assert error.value.details["mutation_outcome"] == "rolled_back"
    assert not controls
    assert executor.objects.invalidate_part.call_count == 2


def test_failed_rollback_reports_partial_state(rig):
    executor, fem, source, target, controls, _ = rig
    controls.fail_commit = True
    executor.session.UndoToMark.side_effect = RuntimeError("undo failed")
    with pytest.raises(NXToolError) as error:
        create(executor, fem, source, target, 0.001)
    assert error.value.details["mutation_outcome"] == "partial"
    assert controls
    assert executor.objects.invalidate_part.call_count == 2

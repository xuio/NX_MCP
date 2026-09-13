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
        shared_interface = False

        def CreateMmcCreateBuilder(self, control):
            if control is not None:
                reader = NS(**vars(control.builder))
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
                control = NS(Tag=50 + len(self), builder=builder)
                if self.shared_interface:
                    rows[0]["face"] = target
                    builder.SourceFace.Value = target
                    source.Tag = 0  # NX retires the source face after canonicalization.
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
    if cause == "corrupt_readback":
        observed = error.value.details["committed_readback_before_rollback"]
        assert observed["source_face_tag"] == target.Tag
        assert error.value.details["requested_face_tags"] == [source.Tag, target.Tag]
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


def test_native_shared_face_requires_membership_on_both_original_bodies(rig):
    executor, fem, source, target, controls, _ = rig
    controls.shared_interface = True
    result = create(executor, fem, source, target, 0.001)
    assert result["selected_face_tags"] == [20, 20]
    assert result["requested_face_tags"] == [10, 20]
    assert result["committed_readback"]["interface_face_candidates_by_original_body"] == [
        [20],
        [20],
    ]
    assert result["connectivity_verified"] is False


def test_second_independent_interface_preserves_first_condition(rig):
    executor, fem, source, target, controls, rows = rig
    first = create(executor, fem, source, target, 0.001)
    first_builder = controls[0].builder
    new_source, new_target = NS(Tag=30, OwningPart=fem), NS(Tag=40, OwningPart=fem)
    rows.extend(
        [
            {
                "face": f,
                "body": NS(Tag=i),
                "bounds": {"minimum": [40, 0, 0], "maximum": [40, 10, 10]},
            }
            for i, f in enumerate([new_source, new_target], start=2)
        ]
    )
    second = create(executor, fem, new_source, new_target, 0.002)
    assert len(controls) == 2
    assert first["preserved_existing_control_tags"] == []
    assert second["preserved_existing_control_tags"] == [50]
    assert controls[0].builder is first_builder
    assert first_builder.SourceFace.Value is source
    assert first_builder.DistTolerance.GetFormula() == "0.001"
    assert second["selected_face_tags"] == [30, 40]


def test_duplicate_pair_rejected_before_second_mutation(rig):
    executor, fem, source, target, controls, _ = rig
    create(executor, fem, source, target, 0.001)
    executor.session.SetUndoMark.reset_mock()
    with pytest.raises(NXToolError, match="already selects"):
        create(executor, fem, target, source, 0.001)
    assert len(controls) == 1
    executor.session.SetUndoMark.assert_not_called()


def test_unreadable_existing_control_rejected_before_mutation(rig):
    executor, fem, source, target, controls, _ = rig
    controls.append(NS(Tag=99))
    with pytest.raises(NXToolError, match="readable mesh-mating"):
        create(executor, fem, source, target, 0.001)
    executor.session.SetUndoMark.assert_not_called()


def test_changed_prior_condition_rolls_back_new_condition_and_restores_prior(rig):
    executor, fem, source, target, controls, rows = rig
    create(executor, fem, source, target, 0.001)
    original = controls[0]
    new_source, new_target = NS(Tag=30, OwningPart=fem), NS(Tag=40, OwningPart=fem)
    rows.extend(
        [
            {
                "face": f,
                "body": NS(Tag=i),
                "bounds": {"minimum": [40, 0, 0], "maximum": [40, 10, 10]},
            }
            for i, f in enumerate([new_source, new_target], start=2)
        ]
    )
    factory = controls.CreateMmcCreateBuilder

    def corrupting_factory(control):
        builder = factory(control)
        if control is None:
            commit = builder.CommitMmcs

            def corrupting_commit():
                result = commit()
                original.builder.ReverseDirection = True
                return result

            builder.CommitMmcs = corrupting_commit
        return builder

    controls.CreateMmcCreateBuilder = corrupting_factory

    def restore(*_):
        controls[:] = [original]
        original.builder.ReverseDirection = False

    executor.session.UndoToMark.side_effect = restore
    with pytest.raises(NXToolError) as error:
        create(executor, fem, new_source, new_target, 0.001)
    assert error.value.details["mutation_outcome"] == "rolled_back"
    assert controls == [original]
    assert original.builder.ReverseDirection is False


@pytest.fixture
def contained_rig(rig, monkeypatch):
    executor, fem, source, target, controls, rows = rig
    rows[0]["bounds"] = {"minimum": [20, 2, 2], "maximum": [20, 8, 8]}
    areas = {10: 36.0, 20: 100.0}
    uf = ModuleType("NXOpen.UF")
    uf.UFSession = NS(GetUFSession=lambda: NS(Sf=NS(FaceAskArea=lambda tag: areas[tag])))
    monkeypatch.setitem(sys.modules, "NXOpen.UF", uf)
    sys.modules["NXOpen"].UF = uf
    sys.modules["NXOpen.CAE"].MMCCreateBuilder.FaceSearchType.AllPairs = 2
    return rig, areas


@pytest.mark.parametrize("reverse", [False, True])
def test_contained_face_requires_shared_full_small_area(contained_rig, reverse):
    (executor, fem, source, target, controls, rows), areas = contained_rig
    controls.shared_interface = True
    factory = controls.CreateMmcCreateBuilder

    def imprinting_factory(control):
        builder = factory(control)
        if control is None:
            commit = builder.CommitMmcs

            def imprint():
                result = commit()
                rows[1]["bounds"] = {"minimum": [20, 2, 2], "maximum": [20, 8, 8]}
                areas[20] = 36.0
                return result

            builder.CommitMmcs = imprint
        return builder

    controls.CreateMmcCreateBuilder = imprinting_factory
    args = (target, source) if reverse else (source, target)
    result = create(executor, fem, *args, 0.001, allow_contained=True)
    assert result["face_match"] == "contained"
    assert result["requested_face_tags"] == ([20, 10] if reverse else [10, 20])
    assert result["native_selection_face_tags"] == [10, 20]
    assert result["selected_face_tags"] == [20, 20]
    assert result["committed_readback"]["contained_face_area_mm2"] == 36
    assert controls.builder.FaceSearchOption == 2
    assert result["mesh_generated"] is False


@pytest.mark.parametrize("defect", ["outside", "separated", "nonplanar", "zero_area"])
def test_contained_invalid_geometry_rejected_before_mutation(contained_rig, defect):
    (executor, fem, source, target, controls, rows), areas = contained_rig
    if defect == "outside":
        rows[0]["bounds"]["minimum"][1] = -1
    elif defect == "separated":
        rows[0]["bounds"]["minimum"][0] = 20.1
        rows[0]["bounds"]["maximum"][0] = 20.1
    elif defect == "nonplanar":
        rows[0]["bounds"]["maximum"][0] = 21
    else:
        areas[10] = 0
    with pytest.raises(NXToolError):
        create(executor, fem, source, target, 0.001, allow_contained=True)
    assert not controls
    executor.session.SetUndoMark.assert_not_called()


def test_invalid_contained_flag_rejected_before_mutation(rig):
    executor, fem, source, target, controls, _ = rig
    with pytest.raises(NXToolError, match="boolean"):
        create(executor, fem, source, target, 0.001, allow_contained="yes")
    executor.session.SetUndoMark.assert_not_called()


def test_contained_mode_rejects_unimprinted_contact(contained_rig):
    (executor, fem, source, target, controls, _), _areas = contained_rig
    with pytest.raises(NXToolError) as error:
        create(executor, fem, source, target, 0.001, allow_contained=True)
    assert error.value.details["mutation_outcome"] == "rolled_back"
    assert not controls


def test_incomplete_shared_area_rolls_back_and_restores_original_areas(contained_rig):
    from copy import deepcopy

    (executor, fem, source, target, controls, rows), areas = contained_rig
    original_rows = [{**row, "bounds": deepcopy(row["bounds"])} for row in rows]
    original_areas = dict(areas)
    controls.shared_interface = True
    factory = controls.CreateMmcCreateBuilder

    def incomplete_factory(control):
        builder = factory(control)
        if control is None:
            commit = builder.CommitMmcs

            def incomplete_imprint():
                result = commit()
                rows[1]["bounds"] = deepcopy(rows[0]["bounds"])
                areas[20] = 35.0
                return result

            builder.CommitMmcs = incomplete_imprint
        return builder

    controls.CreateMmcCreateBuilder = incomplete_factory

    def restore(*_):
        controls.clear()
        source.Tag, target.Tag = 10, 20
        rows[:] = original_rows
        areas.clear()
        areas.update(original_areas)

    executor.session.UndoToMark.side_effect = restore
    with pytest.raises(NXToolError, match="complete smaller face") as error:
        create(executor, fem, source, target, 0.001, allow_contained=True)
    assert error.value.details["mutation_outcome"] == "rolled_back"
    assert areas == {10: 36.0, 20: 100.0}
    assert not controls

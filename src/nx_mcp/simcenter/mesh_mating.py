"""Explicit pre-mesh glue-coincident condition; connectivity is verified after meshing."""

import math

from nx_mcp.runtime import NXToolError


def create(executor, fem, source, target, tolerance_mm):
    import NXOpen.CAE as cae

    from nx_mcp.simcenter.selections import face_inventory
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    nx, session = executor.nxopen, executor.session
    if not isinstance(fem, cae.FemPart) or session.Parts.BaseWork != fem:
        raise NXToolError("NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate the standalone FEM")
    if fem.PartUnits != nx.BasePart.Units.Millimeters:
        raise NXToolError("NX_SIM_UNITS", "Mesh mating requires a millimeter FEM")
    if (
        type(tolerance_mm) not in (int, float)
        or not math.isfinite(tolerance_mm)
        or not 0 < tolerance_mm <= 0.1
    ):
        raise NXToolError("NX_INVALID_ARGUMENT", "tolerance_mm must be finite in (0,0.1]")
    if source.OwningPart != fem or target.OwningPart != fem or source.Tag == target.Tag:
        raise NXToolError("NX_SIM_SELECTION_OWNER", "Select two distinct FEM prototype faces")
    controls = fem.BaseFEModel.MeshControls
    if fem.BaseFEModel.MeshManager.GetMeshes() or list(controls):
        raise NXToolError(
            "NX_SIM_MESH_PRECONDITION", "Requires no existing meshes or mesh controls"
        )
    rows = face_inventory(session, fem)["rows"]
    by_tag = {int(row["face"].Tag): row for row in rows}
    if int(source.Tag) not in by_tag or int(target.Tag) not in by_tag:
        raise NXToolError("NX_SIM_SELECTION_OWNER", "Faces must belong to enumerated FEM bodies")
    a, b = by_tag[int(source.Tag)], by_tag[int(target.Tag)]
    if a["body"].Tag == b["body"].Tag:
        raise NXToolError("NX_INVALID_ARGUMENT", "Select faces on two different FEM bodies")
    if any(
        abs(x - y) > tolerance_mm
        for key in ("minimum", "maximum")
        for x, y in zip(a["bounds"][key], b["bounds"][key], strict=True)
    ):
        raise NXToolError("NX_INVALID_ARGUMENT", "Face bounds do not coincide within tolerance")
    require_solver_idle()

    def snapshot():
        inventory = face_inventory(session, fem)["rows"]
        return {
            "controls": sorted(int(c.Tag) for c in controls),
            "expressions": sorted(int(e.Tag) for e in fem.Expressions),
            "faces": [(int(r["body"].Tag), int(r["face"].Tag), r["bounds"]) for r in inventory],
            "meshes": sorted(int(m.Tag) for m in fem.BaseFEModel.MeshManager.GetMeshes()),
        }

    before = snapshot()
    affected = [fem] + [p for p in session.Parts if isinstance(p, cae.SimPart) and p.FemPart == fem]
    part_ids = [executor._part_id(p) for p in affected]
    mark = session.SetUndoMark(
        nx.Session.MarkVisibility.Visible, "NX MCP glue coincident mesh faces"
    )
    builder = None
    committed_readback = None
    try:
        builder = controls.CreateMmcCreateBuilder(None)
        builder.Type = cae.MMCCreateBuilder.Types.Manual
        builder.MeshMatingOption = cae.MMCCreateBuilder.MeshMatingType.GlueCoincident
        builder.FaceSearchOption = cae.MMCCreateBuilder.FaceSearchType.IdenticalPairsOnly
        builder.ReverseDirection = False
        for expression in (builder.DistTolerance, builder.SnapTolerance):
            if expression.Units.Name != "MilliMeter":
                raise ValueError("Native mating tolerance is not in millimeters")
            expression.RightHandSide = str(float(tolerance_mm))
        builder.SourceFace.Value = source
        builder.TargetFace.Value = target
        builder.PrintLogOnInfoWindow(False)
        created = list(builder.CommitMmcs())
        builder.Destroy()
        builder = None
        if len(created) != 1 or int(created[0].Tag) not in {int(c.Tag) for c in controls}:
            raise ValueError("Expected exactly one registered mesh-mating condition")
        reader = controls.CreateMmcCreateBuilder(created[0])
        try:
            committed_readback = {
                "mode": str(reader.MeshMatingOption),
                "source_face_tag": int(reader.SourceFace.Value.Tag),
                "target_face_tag": int(reader.TargetFace.Value.Tag),
                "reverse_direction": bool(reader.ReverseDirection),
                "distance_tolerance": reader.DistTolerance.GetFormula(),
                "snap_tolerance": reader.SnapTolerance.GetFormula(),
                "distance_units": reader.DistTolerance.Units.Name,
                "snap_units": reader.SnapTolerance.Units.Name,
            }
            if (
                reader.MeshMatingOption != cae.MMCCreateBuilder.MeshMatingType.GlueCoincident
                or reader.SourceFace.Value.Tag != source.Tag
                or reader.TargetFace.Value.Tag != target.Tag
                or reader.ReverseDirection
                or any(
                    not math.isclose(float(e.GetFormula()), tolerance_mm, rel_tol=0, abs_tol=1e-12)
                    for e in (reader.DistTolerance, reader.SnapTolerance)
                )
            ):
                raise ValueError("Committed mesh mating differs from requested faces/settings")
        finally:
            reader.Destroy()
        if fem.BaseFEModel.MeshManager.GetMeshes():
            raise ValueError("Mesh mating unexpectedly generated a mesh")
        return {
            "control": created[0],
            "kind": "glue_coincident",
            "tolerance_mm": tolerance_mm,
            "selected_face_tags": [int(source.Tag), int(target.Tag)],
            "saved": False,
            "mesh_generated": False,
            "connectivity_verified": False,
            "references_invalidated": [p.FullPath for p in affected],
            "scope": "Native condition and selection readback only; exact coincidence, generated connectivity and solver behavior require validation",
        }
    except Exception as error:
        outcome = "rolled_back"
        try:
            if builder is not None:
                builder.Destroy()
                builder = None
            session.UndoToMark(mark, None)
            if snapshot() != before:
                raise ValueError("Mesh/control/expression/face inventory changed after rollback")
            session.DeleteUndoMark(mark, None)
        except Exception:
            outcome = "partial"
        raise NXToolError(
            "NX_SIM_MESH_MATING_FAILED",
            str(error),
            nx_code=getattr(error, "ErrorCode", None),
            details={
                "mutation_outcome": outcome,
                "committed_readback_before_rollback": committed_readback,
                "requested_face_tags": [int(source.Tag), int(target.Tag)],
                "requested_tolerance_mm": tolerance_mm,
                "rollback_scope": "Control/expression/mesh identities and face bounds; not complete geometric equivalence",
            },
        ) from error
    finally:
        try:
            if builder is not None:
                builder.Destroy()
        finally:
            for part_id in part_ids:
                executor.objects.invalidate_part(part_id)

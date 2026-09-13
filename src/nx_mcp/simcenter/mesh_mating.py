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
    if fem.BaseFEModel.MeshManager.GetMeshes():
        raise NXToolError("NX_SIM_MESH_PRECONDITION", "Requires no existing meshes")
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

    def control_settings(control):
        reader = controls.CreateMmcCreateBuilder(control)
        try:
            return {
                "mode": str(reader.MeshMatingOption),
                "source_face_tag": int(reader.SourceFace.Value.Tag),
                "target_face_tag": int(reader.TargetFace.Value.Tag),
                "reverse_direction": bool(reader.ReverseDirection),
                "distance_tolerance": reader.DistTolerance.GetFormula(),
                "snap_tolerance": reader.SnapTolerance.GetFormula(),
                "distance_units": reader.DistTolerance.Units.Name,
                "snap_units": reader.SnapTolerance.Units.Name,
            }
        finally:
            reader.Destroy()

    try:
        existing_settings = {int(c.Tag): control_settings(c) for c in controls}
    except Exception as error:
        raise NXToolError(
            "NX_SIM_MESH_PRECONDITION",
            "Existing controls must be readable mesh-mating conditions; create sizing controls later",
        ) from error
    existing_face_tags = {
        settings[key]
        for settings in existing_settings.values()
        for key in ("source_face_tag", "target_face_tag")
    }
    existing_face_rows = [
        (int(row["body"].Tag), int(row["face"].Tag), row["bounds"])
        for row in rows
        if int(row["face"].Tag) in existing_face_tags
    ]
    if existing_face_tags - {row[1] for row in existing_face_rows}:
        raise NXToolError(
            "NX_SIM_READBACK_MISMATCH", "An existing mating face is absent from FEM geometry"
        )
    requested_pair = {int(source.Tag), int(target.Tag)}
    if any(
        requested_pair == {settings["source_face_tag"], settings["target_face_tag"]}
        for settings in existing_settings.values()
    ):
        raise NXToolError(
            "NX_SIM_NAME_CONFLICT", "A mating condition already selects this face pair"
        )

    def snapshot():
        inventory = face_inventory(session, fem)["rows"]
        return {
            "controls": sorted(int(c.Tag) for c in controls),
            "control_settings": {int(c.Tag): control_settings(c) for c in controls},
            "expressions": sorted(int(e.Tag) for e in fem.Expressions),
            "faces": [(int(r["body"].Tag), int(r["face"].Tag), r["bounds"]) for r in inventory],
            "meshes": sorted(int(m.Tag) for m in fem.BaseFEModel.MeshManager.GetMeshes()),
        }

    requested_face_tags = [int(source.Tag), int(target.Tag)]
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
        after_controls = {int(c.Tag): c for c in controls}
        if (
            len(created) != 1
            or set(after_controls) - set(existing_settings) != {int(created[0].Tag)}
            or not set(existing_settings).issubset(after_controls)
        ):
            raise ValueError(
                "Expected exactly one new condition and all existing conditions retained"
            )
        if any(
            control_settings(after_controls[tag]) != settings
            for tag, settings in existing_settings.items()
        ):
            raise ValueError("An existing mesh-mating condition changed during creation")
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
            # Glue Coincident can canonicalize the two CAE faces to one shared face.
            # Validate the resulting face against each original body and interface
            # bounds rather than accepting arbitrary topology changes or stale IDs.
            after_rows = face_inventory(session, fem)["rows"]
            retained_face_rows = [
                (int(row["body"].Tag), int(row["face"].Tag), row["bounds"])
                for row in after_rows
                if int(row["face"].Tag) in existing_face_tags
            ]
            if retained_face_rows != existing_face_rows:
                raise ValueError("Existing mating face membership or bounds changed")
            candidates = []
            for original in (a, b):
                candidates.append(
                    {
                        int(row["face"].Tag)
                        for row in after_rows
                        if row["body"].Tag == original["body"].Tag
                        and all(
                            abs(x - y) <= tolerance_mm
                            for key in ("minimum", "maximum")
                            for x, y in zip(
                                row["bounds"][key], original["bounds"][key], strict=True
                            )
                        )
                    }
                )
            committed_readback["interface_face_candidates_by_original_body"] = [
                sorted(tags) for tags in candidates
            ]
            if (
                reader.MeshMatingOption != cae.MMCCreateBuilder.MeshMatingType.GlueCoincident
                or candidates[0] != {int(reader.SourceFace.Value.Tag)}
                or candidates[1] != {int(reader.TargetFace.Value.Tag)}
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
            "preserved_existing_control_tags": sorted(existing_settings),
            "tolerance_mm": tolerance_mm,
            "requested_face_tags": requested_face_tags,
            "committed_readback": committed_readback,
            "selected_face_tags": [
                committed_readback["source_face_tag"],
                committed_readback["target_face_tag"],
            ],
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
                "requested_face_tags": requested_face_tags,
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

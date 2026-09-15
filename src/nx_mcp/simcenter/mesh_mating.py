"""Explicit pre-mesh glue-coincident condition; connectivity is verified after meshing."""

import math

from nx_mcp.runtime import NXToolError


def create(
    executor, fem, source, target, tolerance_mm, allow_contained=False,
    area_relative_tolerance=1e-6,
):
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
    if type(allow_contained) is not bool:
        raise NXToolError("NX_INVALID_ARGUMENT", "allow_contained must be a boolean")
    if (
        type(area_relative_tolerance) not in (int, float)
        or not math.isfinite(area_relative_tolerance)
        or not 0 < area_relative_tolerance <= 2e-4
        or (not allow_contained and area_relative_tolerance != 1e-6)
    ):
        raise NXToolError(
            "NX_INVALID_ARGUMENT",
            "area_relative_tolerance must be finite in (0,2e-4]; changing it requires contained mode",
        )
    if source.OwningPart != fem or target.OwningPart != fem or source.Tag == target.Tag:
        raise NXToolError("NX_SIM_SELECTION_OWNER", "Select two distinct FEM prototype faces")
    requested_face_tags = [int(source.Tag), int(target.Tag)]
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
    contained = None
    if allow_contained:
        import NXOpen.UF as uf

        sf = uf.UFSession.GetUFSession().Sf
        areas = [float(sf.FaceAskArea(row["face"].Tag)) for row in (a, b)]
        if any(not math.isfinite(area) or area <= 0 for area in areas):
            raise NXToolError("NX_SIM_READBACK_MISMATCH", "Invalid native face area")
        small, large = (a, b) if areas[0] <= areas[1] else (b, a)
        axes = [
            axis
            for axis in range(3)
            if all(
                row["bounds"]["maximum"][axis] - row["bounds"]["minimum"][axis] <= tolerance_mm
                for row in (small, large)
            )
        ]
        if len(axes) != 1:
            raise NXToolError(
                "NX_INVALID_ARGUMENT", "Contained mode requires axis-aligned planar face bounds"
            )
        axis = axes[0]
        if any(
            abs(small["bounds"][key][axis] - large["bounds"][key][axis]) > tolerance_mm
            for key in ("minimum", "maximum")
        ):
            raise NXToolError(
                "NX_INVALID_ARGUMENT", "Contained faces must share a plane within tolerance"
            )
        if not all(
            small["bounds"]["minimum"][i] >= large["bounds"]["minimum"][i] - tolerance_mm
            and small["bounds"]["maximum"][i] <= large["bounds"]["maximum"][i] + tolerance_mm
            for i in range(3)
            if i != axis
        ):
            raise NXToolError(
                "NX_INVALID_ARGUMENT",
                "Smaller face bounds must lie within the larger face bounds",
            )
        contained = {"bounds": small["bounds"], "area_mm2": min(areas), "axis": axis}
        # Select the smaller face as native source. Both original body memberships
        # are still checked after NX imprints and canonicalizes the interface.
        source, target = small["face"], large["face"]
        a, b = small, large
    elif any(
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
            "selected_face_areas_mm2": {
                tag: float(sf.FaceAskArea(tag)) for tag in requested_face_tags
            }
            if contained
            else None,
        }

    native_selection_face_tags = [int(source.Tag), int(target.Tag)]
    before = snapshot()
    affected = [fem] + [p for p in session.Parts if isinstance(p, cae.SimPart) and p.FemPart == fem]
    part_ids = [executor._part_id(p) for p in affected]
    expected_face_search = (
        cae.MMCCreateBuilder.FaceSearchType.AllPairs
        if contained
        else cae.MMCCreateBuilder.FaceSearchType.IdenticalPairsOnly
    )
    mark = session.SetUndoMark(
        nx.Session.MarkVisibility.Visible, "NX MCP glue coincident mesh faces"
    )
    builder = None
    committed_readback = None
    try:
        builder = controls.CreateMmcCreateBuilder(None)
        builder.Type = cae.MMCCreateBuilder.Types.Manual
        builder.MeshMatingOption = cae.MMCCreateBuilder.MeshMatingType.GlueCoincident
        # This is a creation-time search hint. NX2606 normalizes it to AllPairs
        # when reopening a manual condition, even after IdenticalPairsOnly.
        # Validate the committed faces/geometry rather than this transient hint.
        builder.FaceSearchOption = expected_face_search
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
                "face_search": str(reader.FaceSearchOption),
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
                                row["bounds"][key],
                                (contained["bounds"] if contained else original["bounds"])[key],
                                strict=True,
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
        if contained:
            if committed_readback["source_face_tag"] != committed_readback["target_face_tag"]:
                raise ValueError("Contained interface was not canonicalized to one shared face")
            area_after = float(sf.FaceAskArea(committed_readback["source_face_tag"]))
            # Retain the measurements even when validation rejects the interface.
            # In particular, curved-face imprints need inspectable native evidence
            # before changing geometry or interpreting the area mismatch.
            committed_readback.update(
                contained_face_area_mm2=area_after if math.isfinite(area_after) else None,
                contained_expected_face_area_mm2=contained["area_mm2"],
                contained_face_area_finite=math.isfinite(area_after),
                contained_area_relative_tolerance=area_relative_tolerance,
                contained_area_absolute_tolerance_mm2=1e-6,
            )
            if not math.isclose(
                area_after, contained["area_mm2"],
                rel_tol=area_relative_tolerance, abs_tol=1e-6,
            ):
                raise ValueError(
                    "Shared interface area does not preserve the complete smaller face"
                )
        if fem.BaseFEModel.MeshManager.GetMeshes():
            raise ValueError("Mesh mating unexpectedly generated a mesh")
        return {
            "control": created[0],
            "kind": "glue_coincident",
            "face_match": "contained" if contained else "identical",
            "contained_preflight": contained,
            "native_selection_face_tags": native_selection_face_tags,
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

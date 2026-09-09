"""Native face-density sizing, separate from mesh generation."""

import math

from nx_mcp.runtime import NXToolError


def validate(faces, size_mm):
    if not isinstance(faces, list) or not 1 <= len(faces) <= 1000:
        raise ValueError("Supply 1..1000 distinct FEM face IDs")
    if type(size_mm) not in (int, float) or not math.isfinite(size_mm) or not 0 < size_mm <= 10000:
        raise ValueError("size_mm must be finite and in (0,10000]")


def edit(executor, fem, control, size_mm):
    """Edit one existing native face control without remeshing or changing targets."""
    validate(["existing"], size_mm)
    import NXOpen.CAE as cae

    from nx_mcp.simcenter.mesh_controls import inspect_control
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    nx, session = executor.nxopen, executor.session
    if not isinstance(fem, cae.FemPart) or session.Parts.BaseWork != fem:
        raise NXToolError("NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate a standalone FEM")
    if fem.PartUnits != nx.BasePart.Units.Millimeters:
        raise NXToolError("NX_SIM_UNITS", "Local sizing requires a millimeter FEM")
    collection = fem.BaseFEModel.MeshControls
    before_tags = {int(c.Tag) for c in collection}
    if control.OwningPart != fem or int(control.Tag) not in before_tags:
        raise NXToolError("NX_SIM_SELECTION_OWNER", "Control must belong to the active FEM")
    require_solver_idle()
    before = inspect_control(fem, control, nx, executor._reference)
    if before.get("kind") != "face_size":
        raise NXToolError("NX_SIM_UNSUPPORTED", "Only face-size controls can be edited here")
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "NX MCP edit face size")
    try:
        builder = collection.CreateBuilder(control)
        try:
            if builder.OverallSize.Units.Name != "MilliMeter":
                raise ValueError("Native local size expression is not millimeters")
            builder.OverallSize.RightHandSide = str(float(size_mm))
            committed = list(builder.CommitDensities())
        finally:
            builder.Destroy()
        if {int(c.Tag) for c in committed} != {int(control.Tag)}:
            raise ValueError("Native edit did not return the original control")
        after = inspect_control(fem, control, nx, executor._reference)
        if (
            after.get("kind") != "face_size"
            or not math.isclose(after["size_mm"], size_mm, rel_tol=1e-12)
            or {f["id"] for f in after["faces"]} != {f["id"] for f in before["faces"]}
            or before_tags != {int(c.Tag) for c in collection}
        ):
            raise ValueError("Committed size, selection or control inventory differs")
        return {
            "control": after,
            "previous_size_mm": before["size_mm"],
            "mesh_regeneration_required": True,
            "results_stale": True,
            "saved": False,
            "mesh_generated": False,
        }
    except Exception as error:
        outcome = "rolled_back"
        try:
            session.UndoToMark(mark, None)
            session.DeleteUndoMark(mark, None)
            restored = inspect_control(fem, control, nx, executor._reference)
            if restored != before or before_tags != {int(c.Tag) for c in collection}:
                raise ValueError("Control state differs after rollback")
        except Exception:
            outcome = "partial"
        raise NXToolError(
            "NX_SIM_LOCAL_SIZE_EDIT_FAILED",
            str(error),
            nx_code=getattr(error, "ErrorCode", None),
            details={
                "mutation_outcome": outcome,
                "next_step": "Inspect mesh controls before retrying",
            },
        ) from error


def create(executor, fem, face_ids, size_mm):
    validate(face_ids, size_mm)
    import NXOpen.CAE as cae

    from nx_mcp.simcenter.mesh_controls import inspect_control
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    nx, session = executor.nxopen, executor.session
    if not isinstance(fem, cae.FemPart) or session.Parts.BaseWork != fem:
        raise NXToolError("NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate a standalone FEM")
    if fem.PartUnits != nx.BasePart.Units.Millimeters:
        raise NXToolError("NX_SIM_UNITS", "Local sizing requires a millimeter FEM")
    faces = [executor.objects.resolve(ref, expected_kind="face") for ref in face_ids]
    expected = {int(f.Tag) for f in faces}
    if len(expected) != len(faces) or any(f.OwningPart != fem for f in faces):
        raise NXToolError(
            "NX_SIM_SELECTION_OWNER", "Supply distinct FEM prototype faces, not SIM occurrences"
        )
    require_solver_idle()
    collection = fem.BaseFEModel.MeshControls
    before = {int(c.Tag) for c in collection}
    for control in collection:
        reader = collection.CreateBuilder(control)
        try:
            if (
                reader.MainType == cae.MeshControlBuilder.Types.FaceDensitySize
                and expected.intersection(int(f.Tag) for f in reader.Selection.GetArray())
            ):
                raise NXToolError(
                    "NX_SIM_CONTROL_OVERLAP",
                    "A selected face already has a local size control; inspect it before editing",
                )
        finally:
            reader.Destroy()
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "NX MCP local face size")
    try:
        builder = collection.CreateBuilder(None)
        try:
            builder.MainType = cae.MeshControlBuilder.Types.FaceDensitySize
            if builder.OverallSize.Units.Name != "MilliMeter":
                raise ValueError("Native local size expression is not millimeters")
            builder.OverallSize.RightHandSide = str(float(size_mm))
            builder.Selection.Add(faces)
            controls = list(builder.CommitDensities())
        finally:
            builder.Destroy()
        if not controls:
            raise ValueError("Native builder returned no local size controls")
        actual_faces = set()
        rows = []
        for control in controls:
            row = inspect_control(fem, control, nx, executor._reference)
            if row.get("kind") != "face_size" or not math.isclose(
                row["size_mm"], size_mm, rel_tol=1e-12
            ):
                raise ValueError("Committed local size differs from request")
            actual_faces.update(
                int(executor.objects.resolve(f["id"], expected_kind="face").Tag)
                for f in row["faces"]
            )
            rows.append(row)
        if actual_faces != expected:
            raise ValueError("Committed face selection differs from request")
        return {
            "controls": rows,
            "control_count": len(rows),
            "face_count": len(expected),
            "size_mm": float(size_mm),
            "saved": False,
            "mesh_generated": False,
            "mesh_regeneration_required": True,
            "results_stale": True,
        }
    except Exception as error:
        outcome = "rolled_back"
        try:
            session.UndoToMark(mark, None)
            session.DeleteUndoMark(mark, None)
            if before != {int(c.Tag) for c in collection}:
                raise ValueError("Control inventory differs after rollback")
        except Exception:
            outcome = "partial"
        raise NXToolError(
            "NX_SIM_LOCAL_SIZE_FAILED",
            str(error),
            nx_code=getattr(error, "ErrorCode", None),
            details={
                "mutation_outcome": outcome,
                "next_step": "Inspect mesh controls and selections before retrying",
            },
        ) from error

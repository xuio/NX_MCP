"""Internal native boundary-layer control authoring; meshing is a separate operation."""

import math

from nx_mcp.runtime import NXToolError


def create_boundary_layers(session, fem, faces, *, first_layer_mm, layers, growth_rate):
    import NXOpen as nx
    import NXOpen.CAE as cae

    if not isinstance(fem, cae.FemPart) or session.Parts.BaseWork != fem:
        raise NXToolError("NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate the target FEM")
    if fem.PartUnits != nx.BasePart.Units.Millimeters:
        raise NXToolError("NX_SIM_UNITS", "Boundary-layer adapter requires a millimeter FEM")
    if type(layers) is not int or not 1 <= layers <= 100:
        raise NXToolError("NX_INVALID_ARGUMENT", "layers must be an integer in [1, 100]")
    if (
        any(
            type(v) not in (int, float) or not math.isfinite(v)
            for v in (first_layer_mm, growth_rate)
        )
        or first_layer_mm <= 0
        or not 1 <= growth_rate <= 3
    ):
        raise NXToolError(
            "NX_INVALID_ARGUMENT",
            "Supply positive finite first-layer thickness and growth rate in [1, 3]",
        )
    if not faces or len(faces) > 1000 or any(f.OwningPart != fem for f in faces):
        raise NXToolError("NX_SIM_SELECTION_OWNER", "Supply 1–1000 FEM-owned wall faces")
    expected = {int(f.Tag) for f in faces}
    if len(expected) != len(faces):
        raise NXToolError("NX_INVALID_ARGUMENT", "Duplicate wall faces")
    collection = fem.BaseFEModel.MeshControls
    before = {int(c.Tag) for c in collection}
    if before:
        raise NXToolError(
            "NX_SIM_CONTROLS_EXIST",
            "Inspect existing controls; this adapter requires no prior mesh controls",
        )
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "NX MCP boundary-layer control")
    builder = None
    try:
        builder = collection.CreateBuilder(None)
        builder.MainType = cae.MeshControlBuilder.Types.BoundaryLayers
        builder.HeightDefinedBy = cae.MeshControlBuilder.HeightDefinedByOption.GrowthRate
        builder.NumberOfLayers = layers
        builder.GrowthRate = float(growth_rate)
        if builder.FirstLayerThickness.Units.Name != "MilliMeter":
            raise NXToolError("NX_SIM_UNITS", "Native first-layer expression is not in millimeters")
        builder.FirstLayerThickness.RightHandSide = str(float(first_layer_mm))
        builder.Selection.Add(faces)
        controls = list(builder.CommitDensities())
        builder.Destroy()
        builder = None
        if len(controls) != 1:
            raise NXToolError(
                "NX_SIM_READBACK_MISMATCH", "Expected one committed boundary-layer control"
            )
        reader = collection.CreateBuilder(controls[0])
        try:
            actual = {int(f.Tag) for f in reader.Selection.GetArray()}
            if (
                actual != expected
                or reader.NumberOfLayers != layers
                or reader.GrowthRate != growth_rate
                or float(reader.FirstLayerThickness.GetFormula()) != first_layer_mm
                or reader.MainType != cae.MeshControlBuilder.Types.BoundaryLayers
                or reader.HeightDefinedBy != cae.MeshControlBuilder.HeightDefinedByOption.GrowthRate
            ):
                raise NXToolError(
                    "NX_SIM_READBACK_MISMATCH", "Layer parameters or wall selection did not persist"
                )
            result = {
                "control": controls[0],
                "face_count": len(actual),
                "body_target_count": len(reader.BlTargetSelection.GetArray()),
                "first_layer_mm": float(reader.FirstLayerThickness.GetFormula()),
                "layers": reader.NumberOfLayers,
                "growth_rate": reader.GrowthRate,
                "native_dimension": reader.BlDimension,
                "saved": False,
                "mesh_generated": False,
                "mesh_regeneration_required": True,
            }
        finally:
            reader.Destroy()
        return result
    except Exception as error:
        try:
            if builder is not None:
                builder.Destroy()
                builder = None
            session.UndoToMark(mark, None)
            if {int(c.Tag) for c in collection} != before:
                raise RuntimeError("Mesh controls remain after rollback")
            session.DeleteUndoMark(mark, None)
        except Exception as recovery:
            raise NXToolError(
                "NX_SIM_ROLLBACK_FAILED",
                "Boundary-layer authoring failed with incomplete rollback",
                details={
                    "operation_error": str(error),
                    "recovery_error": str(recovery),
                    "mutation_outcome": "partial",
                },
            ) from error
        raise
    finally:
        if builder is not None:
            builder.Destroy()

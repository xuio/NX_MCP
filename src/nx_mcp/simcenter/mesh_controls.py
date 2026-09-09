"""Native mesh-control inventory; inspection does not generate or validate meshes."""

import math

from nx_mcp.runtime import NXToolError


def inspect_control(fem, control, nx, reference):
    import NXOpen.CAE as cae

    builder = fem.BaseFEModel.MeshControls.CreateBuilder(control)
    try:
        result = {
            "control": reference(control, "simulation_mesh_control", fem, "control"),
            "native_type": str(builder.MainType),
        }
        if builder.MainType != cae.MeshControlBuilder.Types.BoundaryLayers:
            return {**result, "inspection_status": "unsupported_control_type"}
        expression = builder.FirstLayerThickness
        value = expression.GetValueUsingUnits(nx.Expression.UnitsOption.Expression)
        if expression.Units is None or not math.isfinite(value):
            raise ValueError("Boundary-layer thickness has no finite unit-bearing value")
        millimeters = fem.UnitCollection.Convert(
            expression.Units, fem.UnitCollection.FindObject("MilliMeter"), value
        )
        faces = list(builder.Selection.GetArray())
        bodies = list(builder.BlTargetSelection.GetArray())
        if len(faces) > 1000 or len(bodies) > 1000:
            raise ValueError("Control target inventory exceeds 1000 objects")
        return {
            **result,
            "kind": "boundary_layers",
            "first_layer_mm": millimeters,
            "thickness_expression": expression.GetFormula(),
            "native_thickness": {"value": value, "units": expression.Units.Name},
            "layers": builder.NumberOfLayers,
            "growth_rate": builder.GrowthRate,
            "height_mode": str(builder.HeightDefinedBy),
            "dimension": str(builder.BlDimension),
            "faces": [reference(f, "face", fem, "face") for f in faces],
            "body_targets": [reference(b, "body", fem, "body") for b in bodies],
            "coordinate_frame": "fem_part_absolute",
            "mesh_effect": "not_verified",
        }
    finally:
        builder.Destroy()


def inventory(session, fem, nx, reference, offset=0, limit=50):
    import NXOpen.CAE as cae

    from nx_mcp.simcenter.property_values import preserved_getter_state

    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
        raise NXToolError("NX_INVALID_ARGUMENT", "offset >=0; limit 1..100")
    if not isinstance(fem, cae.FemPart) or session.Parts.BaseWork != fem:
        raise NXToolError("NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate a standalone FEM")
    controls = list(fem.BaseFEModel.MeshControls)
    rows = []
    with preserved_getter_state(nx):
        for control in controls[offset : offset + limit]:
            try:
                rows.append(inspect_control(fem, control, nx, reference))
            except Exception as error:
                rows.append(
                    {
                        "control": reference(control, "simulation_mesh_control", fem, "control"),
                        "inspection_status": "read_failed",
                        "message": str(error),
                        "nx_code": getattr(error, "ErrorCode", None),
                    }
                )
    return {
        "controls": rows,
        "total": len(controls),
        "next_offset": offset + limit if offset + limit < len(controls) else None,
        "mesh_generated": False,
        "mesh_quality": "not_verified",
    }

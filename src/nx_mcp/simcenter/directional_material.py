"""Native orthotropic thermal material creation; axes are material axes, not global."""

import math
from contextlib import suppress

from nx_mcp.runtime import NXToolError


def validate_properties(conductivities, density, heat_capacity, name, provenance):
    if not isinstance(conductivities, (list, tuple)) or len(conductivities) != 3:
        raise NXToolError(
            "NX_INVALID_ARGUMENT", "Provide three material-axis conductivities in W/(m K)"
        )
    values = [*conductivities, density, heat_capacity]
    if any(
        isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0
        for v in values
    ):
        raise NXToolError(
            "NX_INVALID_ARGUMENT", "Thermal properties must be positive finite numbers"
        )
    if not isinstance(name, str) or not name.strip() or len(name) > 100:
        raise NXToolError("NX_INVALID_ARGUMENT", "Material name must contain 1..100 characters")
    if not isinstance(provenance, str) or not provenance.strip() or len(provenance) > 2000:
        raise NXToolError("NX_INVALID_ARGUMENT", "Provide property provenance (1..2000 characters)")
    return {
        "ThermalConductivity": (float(conductivities[0]), "ThermalConductivity_Metric3"),
        "ThermalConductivity2": (float(conductivities[1]), "ThermalConductivity_Metric3"),
        "ThermalConductivity3": (float(conductivities[2]), "ThermalConductivity_Metric3"),
        "MassDensity": (float(density), "KilogramPerCubicMeter"),
        "SpecificHeat": (float(heat_capacity), "SpecificHeat_Metric2"),
    }


def create_orthotropic(
    session, nx, fem, *, conductivities, density, heat_capacity, name, provenance
):
    """Create without assignment/save; return native material and actual scalar readback."""
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    values = validate_properties(conductivities, density, heat_capacity, name, provenance)
    require_solver_idle()
    materials = fem.MaterialManager.PhysicalMaterials
    if any(m.Name.casefold() == name.casefold() for m in materials):
        raise NXToolError("NX_SIM_NAME_CONFLICT", "Material already exists in the selected FEM")
    units = {key: fem.UnitCollection.FindObject(unit) for key, (_, unit) in values.items()}
    _, status = session.Parts.SetDisplay(fem, False, False)
    if status:
        status.Dispose()
    session.Parts.SetWork(fem)
    mark = session.SetUndoMark(
        nx.Session.MarkVisibility.Visible, "NX MCP orthotropic thermal material"
    )
    builder = None
    try:
        builder = materials.CreatePhysicalMaterialBuilder(nx.PhysicalMaterial.Type.Orthotropic)
        builder.Name, builder.Description = name, provenance
        builder.AddToMaterialLibraryToggle = False
        for key, (value, _) in values.items():
            expression = fem.Expressions.CreateSystemNumberExpression(str(value), units[key])
            wrapper = fem.FieldManager.CreateScalarFieldWrapperWithExpression(expression)
            builder.PropertyTable.SetScalarFieldWrapperPropertyValue(key, wrapper)
        material = builder.Commit()
        actual = {}
        for key, (expected, _) in values.items():
            wrapper = material.GetPropTable().GetScalarFieldWrapperPropertyValue(key)
            expression = wrapper.GetExpression()
            if expression is None or expression.Units != units[key]:
                raise NXToolError(
                    "NX_SIM_READBACK_MISMATCH",
                    "Committed material expression or unit differs",
                    details={"property": key},
                )
            value = expression.GetValueUsingUnits(nx.Expression.UnitsOption.Expression)
            if not math.isclose(value, expected, rel_tol=1e-10, abs_tol=1e-12):
                raise NXToolError(
                    "NX_SIM_READBACK_MISMATCH",
                    "Committed material value differs",
                    details={"property": key},
                )
            actual[key] = {
                "value": value,
                "unit": expression.Units.Name,
                "symbol": expression.Units.Symbol,
            }
        return (
            material,
            {
                "properties": actual,
                "provenance": provenance,
                "coordinate_frame": "material_axes",
                "orientation_assigned": False,
                "collector_assignment": False,
                "saved": False,
                "solver_verified": False,
            },
            mark,
        )
    except Exception as error:
        if builder is not None:
            with suppress(Exception):
                builder.Destroy()
            builder = None
        outcome = "rolled_back"
        try:
            session.UndoToMark(mark, None)
            session.DeleteUndoMark(mark, None)
        except Exception:
            outcome = "partial"
        raise NXToolError(
            "NX_SIM_MATERIAL_FAILED",
            "Orthotropic material creation failed",
            nx_code=getattr(error, "ErrorCode", None),
            details={"mutation_outcome": outcome, "cause_code": getattr(error, "code", None)},
        ) from error
    finally:
        if builder is not None:
            builder.Destroy()

"""Internal constant-property fluid material authoring on the NX thread."""

import math

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.properties import read_properties


def assign_fluid_material(
    session, fem, collectors, name, provenance, density, viscosity, conductivity, heat_capacity
):
    import NXOpen as nx
    import NXOpen.CAE as cae

    if session.Parts.BaseWork != fem or not isinstance(fem, cae.FemPart):
        raise NXToolError("NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate the selected FEM first")
    values = {
        "MassDensity": (density, "KilogramPerCubicMeter"),
        "DynamicVisc": (viscosity, "DynamicViscosity_PascalSecond"),
        "ThermalConductivity": (conductivity, "ThermalConductivity_Metric3"),
        "SpecificHeat": (heat_capacity, "SpecificHeat_Metric2"),
    }
    if any(
        type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v, _ in values.values()
    ):
        raise NXToolError(
            "NX_INVALID_ARGUMENT", "Supply positive finite fluid properties in SI units"
        )
    if not name.strip() or not provenance.strip():
        raise NXToolError("NX_INVALID_ARGUMENT", "Supply a name and property provenance")
    if not collectors or any(
        c.OwningPart != fem or c.CollectorNeutralType != "Fluid" for c in collectors
    ):
        raise NXToolError(
            "NX_SIM_SELECTION_OWNER", "Select fluid collectors owned by the active FEM"
        )
    materials = fem.MaterialManager.PhysicalMaterials
    before = {int(m.Tag) for m in materials}
    if any(m.Name.casefold() == name.casefold() for m in materials):
        raise NXToolError("NX_SIM_NAME_CONFLICT", "Material name already exists")
    tables = [
        c.ElementPropertyTable.GetNamedPropertyTablePropertyValue("Fluid Property").PropertyTable
        for c in collectors
    ]
    previous = [t.GetMaterialPropertyValue("material") for t in tables]
    if any(material is not None for _, material in previous):
        raise NXToolError("NX_SIM_MATERIAL_EXISTS", "Explicit fluid material already assigned")
    units = {key: fem.UnitCollection.FindObject(unit) for key, (_, unit) in values.items()}
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "NX MCP fluid material")
    builder = None
    try:
        builder = materials.CreatePhysicalMaterialBuilder(nx.PhysicalMaterial.Type.Fluid)
        builder.Name = name
        builder.Description = provenance
        builder.AddToMaterialLibraryToggle = False
        for key, (value, _) in values.items():
            expr = fem.Expressions.CreateSystemNumberExpression(str(float(value)), units[key])
            wrapper = fem.FieldManager.CreateScalarFieldWrapperWithExpression(expr)
            builder.PropertyTable.SetScalarFieldWrapperPropertyValue(key, wrapper)
        material = builder.Commit()
        builder.Destroy()
        builder = None
        for table in tables:
            options = fem.NewMaterialOptions()
            try:
                options.Material = material
                options.MaterialInherited = False
                table.SetPhysicalMaterialPropertyValue("material", options)
            finally:
                options.Dispose()
            inherited, actual = table.GetMaterialPropertyValue("material")
            if inherited or actual != material:
                raise NXToolError("NX_SIM_READBACK_MISMATCH", "Fluid collector assignment differs")
        props = read_properties(material.GetPropTable(), nx)
        for key, (value, unit) in values.items():
            actual = next(p for p in props if p["name"] == key)
            if float(actual["expression"]) != value or actual["units"] != unit:
                raise NXToolError(
                    "NX_SIM_READBACK_MISMATCH", "Fluid material value or unit differs"
                )
        return {
            "material": material,
            "properties": props,
            "provenance": provenance,
            "collector_count": len(collectors),
            "inherited": False,
            "solver_control_semantics": "not_verified",
            "saved": False,
        }
    except Exception as error:
        try:
            if builder is not None:
                builder.Destroy()
                builder = None
            session.UndoToMark(mark, None)
            if {int(m.Tag) for m in materials} != before or any(
                t.GetMaterialPropertyValue("material") != old
                for t, old in zip(tables, previous, strict=True)
            ):
                raise RuntimeError("Material state differs after rollback")
            session.DeleteUndoMark(mark, None)
        except Exception as recovery:
            raise NXToolError(
                "NX_SIM_ROLLBACK_FAILED",
                "Fluid material creation failed with incomplete recovery",
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

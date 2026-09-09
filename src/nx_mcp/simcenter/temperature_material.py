"""Isotropic thermal materials with native temperature tables and constant density."""

import math

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter import scalar_tables


def validate(name, conductivity_samples, heat_capacity_samples, density, provenance):
    if not isinstance(name, str) or not name.strip() or len(name) > 80:
        raise NXToolError("NX_INVALID_ARGUMENT", "Material name must contain 1..80 characters")
    if type(density) not in (int, float) or not math.isfinite(density) or density <= 0:
        raise NXToolError("NX_INVALID_ARGUMENT", "Density must be positive finite kg/m³")
    manifests = {}
    for key, quantity, suffix, samples in [
        ("ThermalConductivity", "conductivity", "_K", conductivity_samples),
        ("SpecificHeat", "heat_capacity", "_CP", heat_capacity_samples),
    ]:
        m = scalar_tables.validate(
            {
                "name": name + suffix,
                "axis": "temperature",
                "quantity": quantity,
                "samples": samples,
                "provenance": provenance,
            }
        )
        if any(y <= 0 for _, y in m["samples"]):
            raise NXToolError(
                "NX_INVALID_ARGUMENT",
                "Conductivity and heat capacity must be positive at every sample",
            )
        manifests[key] = m
    low = max(m["samples"][0][0] for m in manifests.values())
    high = min(m["samples"][-1][0] for m in manifests.values())
    if low >= high:
        raise NXToolError(
            "NX_SIM_FIELD_COVERAGE", "Material tables must share a nonzero temperature interval"
        )
    return manifests, [low, high]


def snapshot(fem):
    return {
        "materials": sorted(int(m.Tag) for m in fem.MaterialManager.PhysicalMaterials),
        "fields": sorted(int(f.Tag) for f in fem.FieldManager.Fields),
        "expressions": sorted(int(e.Tag) for e in fem.Expressions),
    }


def verify(material, nx, manifests, density):
    from nx_mcp.simcenter.properties import read_properties

    props = read_properties(material.GetPropTable(), nx)
    by_name = {p.get("name"): p for p in props}
    for key, m in manifests.items():
        row = by_name[key]
        if row.get("field_scale") != 1.0 or row.get("field_definition", {}).get("manifest") != m:
            raise NXToolError(
                "NX_SIM_READBACK_MISMATCH", "Material field definition or scale differs"
            )
    for key in ["ThermalConductivityControl", "SpecificHeatControl"]:
        if by_name[key].get("value") != 0:
            raise NXToolError("NX_SIM_READBACK_MISMATCH", "Material property control differs")
    row = by_name["MassDensityConstant"]
    if row.get("units") != "KilogramPerCubicMeter" or not math.isclose(
        float(row["expression"]), density, rel_tol=1e-12
    ):
        raise NXToolError("NX_SIM_READBACK_MISMATCH", "Material density or unit differs")
    return [
        by_name[k]
        for k in [
            "ThermalConductivity",
            "SpecificHeat",
            "ThermalConductivityControl",
            "SpecificHeatControl",
            "MassDensityConstant",
        ]
    ]


def create(session, fem, name, conductivity_samples, heat_capacity_samples, density, provenance):
    import NXOpen as nx
    import NXOpen.CAE as cae

    from nx_mcp.simcenter.distributed_heat import preflight
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    with preflight():
        manifests, domain = validate(
            name, conductivity_samples, heat_capacity_samples, density, provenance
        )
        if not isinstance(fem, cae.FemPart) or session.Parts.BaseWork != fem:
            raise NXToolError("NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate the selected FEM first")
        if fem.PartUnits != nx.BasePart.Units.Millimeters:
            raise NXToolError("NX_SIM_UNSUPPORTED_UNITS", "This adapter requires a millimeter FEM")
        if any(m.Name.casefold() == name.casefold() for m in fem.MaterialManager.PhysicalMaterials):
            raise NXToolError("NX_SIM_NAME_CONFLICT", "Material already exists")
        if {m["name"].casefold() for m in manifests.values()} & {
            f.Name.casefold() for f in fem.FieldManager.Fields
        }:
            raise NXToolError("NX_SIM_NAME_CONFLICT", "Material field name already exists")
        require_solver_idle()
    before = snapshot(fem)
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "NX MCP temperature material")
    builder = None
    try:
        tables = {
            key: scalar_tables.create(session, fem, m, allow_fem=True).pop("table")
            for key, m in manifests.items()
        }
        builder = fem.MaterialManager.PhysicalMaterials.CreatePhysicalMaterialBuilder(
            nx.PhysicalMaterial.Type.Isotropic
        )
        builder.Name = name
        builder.Description = provenance
        builder.AddToMaterialLibraryToggle = False
        for key, table in tables.items():
            builder.PropertyTable.SetScalarFieldWrapperPropertyValue(
                key, fem.FieldManager.CreateScalarFieldWrapperWithField(table, 1.0)
            )
        for key in ["ThermalConductivityControl", "SpecificHeatControl"]:
            builder.PropertyTable.SetIntegerPropertyValue(key, 0)
        expr = fem.Expressions.CreateSystemNumberExpression(
            str(float(density)), fem.UnitCollection.FindObject("KilogramPerCubicMeter")
        )
        builder.PropertyTable.SetScalarFieldWrapperPropertyValue(
            "MassDensityConstant", fem.FieldManager.CreateScalarFieldWrapperWithExpression(expr)
        )
        material = builder.Commit()
        builder.Destroy()
        builder = None
        props = verify(material, nx, manifests, density)
        if material.Name != name or material.GetDescription() != provenance:
            raise NXToolError("NX_SIM_READBACK_MISMATCH", "Material name/provenance differs")
        return {
            "material": material,
            "fields": tables,
            "properties": props,
            "temperature_domain_k": domain,
            "density_kg_m3": float(density),
            "provenance": provenance,
            "assigned": False,
            "saved": False,
            "solver_launched": False,
            "numerical_acceptance": "not_established",
            "coverage_scope": "common table domain; actual solution temperatures not validated",
        }
    except Exception as error:
        issues = []
        if builder is not None:
            try:
                builder.Destroy()
            except Exception:
                issues.append("builder_destroy")
        try:
            session.UndoToMark(mark, None)
            if snapshot(fem) != before:
                issues.append("snapshot_mismatch")
            session.DeleteUndoMark(mark, None)
        except Exception:
            issues.append("undo")
        raise NXToolError(
            "NX_SIM_RECOVERY_INCOMPLETE"
            if issues
            else getattr(error, "code", "NX_SIM_AUTHORING_FAILED"),
            "Temperature material creation failed",
            nx_code=getattr(error, "nx_code", getattr(error, "ErrorCode", None)),
            details={
                "mutation_outcome": "partial" if issues else "rolled_back",
                "cleanup_issues": issues,
                "verification_scope": "material, field and expression identities; creation only",
            },
        ) from error

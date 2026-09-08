"""Read stock material definitions through documented library-query APIs."""


def run(executor):
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    sim = executor.session.Parts.BaseWork
    if "E-finned-density-path-20260908-r1" not in sim.FullPath:
        raise ValueError("Activate the retained isolated density diagnostic")
    materials = sim.FemPart.MaterialManager.PhysicalMaterials
    before = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    names = list(materials.GetMaterialsFromLibrary(""))
    selected = [
        n for n in names if any(word in n.casefold() for word in ("air", "water", "helium"))
    ][:12]
    rows = []
    for name in selected:
        keys = list(materials.GetMaterialSpecifiedPropertyNeutralNames("", name))
        data = {"name": name, "property_names": keys, "properties": []}
        for key in keys:
            if key in (
                "MaterialType",
                "DensityControl",
                "MassDensity",
                "MassDensityTempPress",
                "MolarMass",
                "GasConstant",
                "ThermalExpansion",
                "SpecificHeatControl",
            ):
                result = materials.GetMaterialPropertyValueAndDisplayName("", name, key)
                data["properties"].append({"name": key, "value_and_display_name": list(result)})
        rows.append(data)
    after = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    if before != after:
        raise ValueError("Read-only library query changed part inventory or flags")
    return {
        "default_library_material_count": len(names),
        "selected": rows,
        "parts_unchanged": True,
        "solver_launched": False,
    }

def run(executor):
    from nx_mcp.simcenter.properties import read_properties
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    sim = executor.session.Parts.BaseWork
    if "E-finned-density-path-20260908-r1" not in sim.FullPath:
        raise ValueError("Expected isolated diagnostic")
    materials = sim.FemPart.MaterialManager.PhysicalMaterials
    before = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    stock = []
    for name in ("Air", "Water", "Helium_Gas"):
        values = {}
        for key in ("Category", "SubCategory", "SCThermalFlowAppliedViews"):
            values[key] = list(materials.GetMaterialPropertyValueAndDisplayName("", name, key))
        stock.append({"name": name, "values": values})
    custom = []
    for mat in materials:
        if mat.Name == "Generic air":
            props = read_properties(mat.GetPropTable(), executor.nxopen)
            custom = [
                p
                for p in props
                if p["name"]
                in (
                    "Category",
                    "SubCategory",
                    "SCThermalFlowAppliedViews",
                    "MaterialType",
                    "DensityControl",
                    "MassDensity",
                    "MolarMass",
                    "GasConstant",
                )
            ]
    after = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    if before != after:
        raise ValueError("Modified flags changed")
    return {"stock": stock, "custom": custom, "parts_unchanged": True, "solver_launched": False}

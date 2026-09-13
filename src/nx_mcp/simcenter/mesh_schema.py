"""Inspect an uncommitted native tetrahedral mesh builder with state restoration."""

from nx_mcp.runtime import NXToolError


def snapshot(fem):
    model = fem.BaseFEModel
    return {
        "meshes": sorted(int(x.Tag) for x in model.MeshManager.GetMeshes()),
        "collectors": sorted(int(x.Tag) for x in model.MeshManager.GetMeshCollectors()),
        "controls": sorted(int(x.Tag) for x in model.MeshControls),
        "bodies": sorted(int(x.Tag) for x in fem.Bodies),
        "expressions": sorted(int(x.Tag) for x in fem.Expressions),
        "modified": bool(fem.IsModified),
    }


def inspect(executor, fem):
    import NXOpen.CAE as cae

    from nx_mcp.simcenter.properties import read_properties
    from nx_mcp.simcenter.property_values import preserved_getter_state
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    nx, session = executor.nxopen, executor.session
    if not isinstance(fem, cae.FemPart) or session.Parts.BaseWork != fem:
        raise NXToolError("NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate the standalone FEM")
    if fem.PartUnits != nx.BasePart.Units.Millimeters:
        raise NXToolError("NX_SIM_UNITS", "Mesh inspection requires a millimeter FEM")
    require_solver_idle()
    before = snapshot(fem)
    try:
        with preserved_getter_state(nx):
            builder = fem.BaseFEModel.MeshManager.CreateMesh3dTetBuilder(None)
            try:
                props = builder.PropertyTable
                descriptors = []
                count = props.GetPropertyCount()
                if count > 512:
                    raise ValueError("Mesh property inventory exceeds 512 entries")
                for index in range(count):
                    name = props.GetPropertyNameByIndex(index)
                    if "licen" in name.lower():
                        continue
                    try:
                        descriptors.append({
                            "name": name,
                            "descriptor": props.GetPropertyDescriptorName(name),
                        })
                    except Exception as error:
                        descriptors.append({"name": name, "inspection_error": str(error)})
                result = {
                    "properties": read_properties(props, nx),
                    "property_descriptors": descriptors,
                    "element_types": list(builder.ElementType.GetElementTypeNames()),
                    "default_element_type": builder.ElementType.ElementTypeName,
                    "automatic_size": bool(builder.AutoSizeOption),
                    "automatic_reset": bool(builder.AutoResetOption),
                    "check_element_size": bool(builder.CheckElementSizeOption),
                    "scope": "Uncommitted builder defaults in this FEM; not existing mesh settings",
                    "enum_value_meanings": "not_inferred",
                    "generated_meshes": 0,
                    "numerical_acceptance": False,
                }
            finally:
                builder.Destroy()
    finally:
        if snapshot(fem) != before:
            raise NXToolError(
                "NX_SIM_RECOVERY_INCOMPLETE", "FEM inventory differs after mesh inspection",
                details={"mutation_outcome": "partial"},
            )
    result["state_restored"] = True
    return result

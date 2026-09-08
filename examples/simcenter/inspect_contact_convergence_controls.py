def run(executor):
    import importlib
    from nx_mcp.simcenter import capabilities, native, release_evidence

    importlib.reload(capabilities)
    importlib.reload(release_evidence)
    native.inspect_capabilities = capabilities.inspect_capabilities
    executor._sim_capabilities.__func__.__globals__["inspect_capabilities"] = (
        capabilities.inspect_capabilities
    )
    sim = executor.session.Parts.BaseWork
    rows = []
    for table in sim.ModelingObjectPropertyTables:
        if table.DescriptorType == "Thermal Parameters":
            props = table.PropertyTable
            rows.append(
                {
                    "name": table.Name,
                    "descriptor": table.DescriptorType,
                    "selector": props.GetIntegerPropertyValue(
                        "Steady State - Convergence Criteria"
                    ),
                    "maximum_change": props.GetBaseScalarWithDataPropertyValue(
                        "Steady State - Maximum Temperature Change"
                    )[0],
                }
            )
    return {
        "document_path": sim.FullPath,
        "thermal_controls": rows,
        "native_mode_meaning": "0 Automatic; 1 Specify per installed Open CAE documentation",
        "solver_launched": False,
    }

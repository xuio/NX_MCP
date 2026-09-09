def run(executor):
    import importlib
    import types

    from nx_mcp import hardened
    from nx_mcp.simcenter import mesh_controls, native, selections

    for module in (native, selections, mesh_controls):
        importlib.reload(module)
    for name in ["mesh_controls", "boundary_layers"]:
        method = types.MethodType(getattr(native.SimcenterMixin, "_sim_" + name), executor)
        setattr(executor, "_sim_" + name, method)
        executor._handlers["nx_sim_" + name] = method
    hardened.READ_ONLY.add("nx_sim_mesh_controls")
    hardened.NON_MODEL.add("nx_sim_boundary_layers")
    return {
        "registered": ["nx_sim_mesh_controls", "nx_sim_boundary_layers"],
        "work": executor.session.Parts.BaseWork.FullPath,
        "display": executor.session.Parts.BaseDisplay.FullPath,
        "solver_launched": False,
    }

def run(executor):
    import importlib
    import types

    from nx_mcp import hardened
    from nx_mcp.simcenter import mesh_plan, native

    importlib.reload(mesh_plan)
    importlib.reload(native)
    method = types.MethodType(native.SimcenterMixin._sim_mesh_plan, executor)
    executor._sim_mesh_plan = method
    executor._handlers["nx_sim_mesh_plan"] = method
    hardened.NON_MODEL.add("nx_sim_mesh_plan")
    return {
        "registered": True,
        "work": executor.session.Parts.BaseWork.FullPath,
        "solver_launched": False,
    }

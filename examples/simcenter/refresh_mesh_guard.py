def run(executor):
    import importlib
    import types

    from nx_mcp.simcenter import mesh_guard, native, native_launch, preparation

    for module in (mesh_guard, preparation, native_launch, native):
        importlib.reload(module)
    method = types.MethodType(native.SimcenterMixin._sim_prepare_solve, executor)
    executor._sim_prepare_solve = method
    executor._handlers["nx_sim_prepare_solve"] = method
    return {"registered": True, "prepare_mesh_guard": True, "launch_mesh_guard": True}

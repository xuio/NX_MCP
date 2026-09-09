def run(executor):
    import importlib
    import types

    from nx_mcp import hardened
    from nx_mcp.simcenter import mesh_state, native

    importlib.reload(mesh_state)
    importlib.reload(native)
    method = types.MethodType(native.SimcenterMixin._sim_mesh_state, executor)
    executor._sim_mesh_state = method
    executor._handlers["nx_sim_mesh_state"] = method
    hardened.READ_ONLY.add("nx_sim_mesh_state")
    return {"registered": True, "handler": "nx_sim_mesh_state"}

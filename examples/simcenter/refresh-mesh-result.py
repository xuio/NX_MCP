def run(executor):
    import importlib
    import types

    from nx_mcp.simcenter import native, result_binding

    importlib.reload(result_binding)
    importlib.reload(native)
    method = types.MethodType(native.SimcenterMixin._sim_result_identity, executor)
    executor._sim_result_identity = method
    executor._handlers["nx_sim_result_identity"] = method
    return {"registered": True, "mesh_result_audit": True}

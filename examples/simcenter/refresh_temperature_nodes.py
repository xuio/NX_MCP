def run(executor):
    import importlib
    import types

    from nx_mcp import hardened
    from nx_mcp.simcenter import native, nodal_results

    importlib.reload(nodal_results)
    importlib.reload(native)
    method = types.MethodType(native.SimcenterMixin._sim_temperature_nodes, executor)
    executor._sim_temperature_nodes = method
    executor._handlers["nx_sim_temperature_nodes"] = method
    hardened.READ_ONLY.add("nx_sim_temperature_nodes")
    return {"registered": True, "handler": "nx_sim_temperature_nodes"}

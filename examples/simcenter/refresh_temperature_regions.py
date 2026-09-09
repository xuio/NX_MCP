def run(executor):
    import importlib
    import types

    from nx_mcp import hardened
    from nx_mcp.simcenter import native, region_results, result_reader

    importlib.reload(region_results)
    importlib.reload(result_reader)
    importlib.reload(native)
    method = types.MethodType(native.SimcenterMixin._sim_temperature_regions, executor)
    executor._sim_temperature_regions = method
    executor._handlers["nx_sim_temperature_regions"] = method
    hardened.READ_ONLY.add("nx_sim_temperature_regions")
    previous = types.MethodType(native.SimcenterMixin._sim_temperature_nodes, executor)
    executor._sim_temperature_nodes = previous
    executor._handlers["nx_sim_temperature_nodes"] = previous
    return {"registered": True, "handler": "nx_sim_temperature_regions"}

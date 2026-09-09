def run(executor):
    import importlib
    import types

    from nx_mcp import hardened
    from nx_mcp.simcenter import local_size, native, remesh

    for module in (local_size, remesh, native):
        importlib.reload(module)
    names = ("face_size_edit", "remesh")
    for name in names:
        method = types.MethodType(getattr(native.SimcenterMixin, "_sim_" + name), executor)
        setattr(executor, "_sim_" + name, method)
        executor._handlers["nx_sim_" + name] = method
        hardened.NON_MODEL.add("nx_sim_" + name)
    return {"registered": list(names), "work_document": executor.session.Parts.BaseWork.FullPath}

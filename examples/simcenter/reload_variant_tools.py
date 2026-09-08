"""Bind only the new variant entry points, preserving the running UI host."""


def run(executor):
    import importlib
    import types

    import nx_mcp.hardened as hardened
    import nx_mcp.simcenter.native as native
    import nx_mcp.simcenter.server as server

    flags = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    importlib.reload(native)
    importlib.reload(server)
    names = ("nx_sim_variant_plan", "nx_sim_variant_create", "nx_sim_variant_receipt")
    bindings = {
        name: types.MethodType(getattr(native.SimcenterMixin, "_" + name[3:]), executor)
        for name in names
    }
    for name, method in bindings.items():
        setattr(executor, "_" + name[3:], method)
        executor._handlers[name] = method
    hardened.READ_ONLY.update(set(names) & server.READ_ONLY)
    hardened.NON_MODEL.update(set(names) & server.NON_MODEL)
    assert flags == {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    return {"registered": list(names), "document_flags_preserved": True, "restart": False}

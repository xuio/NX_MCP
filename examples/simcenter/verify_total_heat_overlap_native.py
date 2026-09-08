def run(executor):
    import importlib
    import types

    from nx_mcp.simcenter import distributed_heat, heat_loads, native, server
    from nx_mcp.simcenter.recovery import authoring_snapshot
    from nx_mcp.simcenter.selections import face_inventory

    importlib.reload(heat_loads)
    importlib.reload(distributed_heat)
    importlib.reload(native)
    importlib.reload(server)
    handler = types.MethodType(native.SimcenterMixin._sim_heat_power, executor)
    executor._sim_heat_power = handler
    executor._handlers["nx_sim_heat_power"] = handler
    s = executor.session
    sim = s.Parts.BaseWork
    assert "distributed-heat-public-20260908-r2" in sim.FullPath
    before = authoring_snapshot(sim)
    flags = [(p.FullPath, bool(p.IsModified)) for p in s.Parts]
    inv = face_inventory(s, sim)
    flux = next(load for load in sim.Simulation.Loads if load.Name == "MCP surface flux")
    _, members = flux.TargetSetManager.GetTargetSetMembers(0)
    prototype = next(r["body"] for r in inv["rows"] if r["face"].Tag == members[0].Obj.Tag)
    component = sim.ComponentAssembly.RootComponent.GetChildren()[0]
    body = component.FindOccurrence(prototype)
    args = {
        "power_w": 0.1,
        "name": "MCP additive total power probe",
        "provenance": "Separate contribution for native test",
    }
    try:
        heat_loads.create_body_power(s, sim, body, **args)
    except Exception as error:
        assert getattr(error, "code", None) == "NX_SIM_OVERLAPPING_HEAT_SOURCE", str(error)
        assert error.details["mutation_outcome"] == "not_started"
        rejected = error.details
    else:
        raise AssertionError("Ownership overlap was accepted without explicit policy")
    assert before == authoring_snapshot(sim)
    mark = s.SetUndoMark(executor.nxopen.Session.MarkVisibility.Visible, "Additive heat acceptance")
    try:
        accepted = heat_loads.create_body_power(
            s, sim, body, overlap_policy="allow_additive", **args
        )
        accepted.pop("load")
        assert accepted["overlaps"] and accepted["overlap_policy"] == "allow_additive"
    finally:
        s.UndoToMark(mark, None)
        s.DeleteUndoMark(mark, None)
    assert before == authoring_snapshot(sim)
    assert flags == [(p.FullPath, bool(p.IsModified)) for p in s.Parts]
    return {
        "rejection": rejected,
        "accepted": accepted,
        "rollback_verified": True,
        "flags_preserved": True,
    }

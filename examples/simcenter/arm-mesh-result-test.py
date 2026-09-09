def run(executor):
    import json
    from pathlib import Path

    from nx_mcp.runtime import NXToolError
    from nx_mcp.simcenter import mesh_state, native_launch
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    if getattr(executor, "_mesh_guard_probe", None) is not None:
        raise ValueError(
            "A mesh-guard probe is already armed; inspect/restore it instead of repeating mutation"
        )
    nx, session = executor.nxopen, executor.session
    sim = session.Parts.BaseWork
    assert type(sim).__name__ == "SimPart" and "V-mesh-guard-positive-20260909-r1" in sim.FullPath
    fem = sim.FemPart
    before = mesh_state.capture(fem)
    flags = [(p.FullPath, bool(p.IsModified)) for p in session.Parts]
    executor._sim_activate(executor._reference(fem, "part", fem, "FEM")["id"])
    labels = fem.BaseFEModel.FenodeLabelMap
    try:
        label = 0
        node = None
        for _ in range(labels.NumNodes):
            label = labels.AskNextNodeLabel(label)
            candidate = labels.GetNode(label)
            p = candidate.Coordinates
            if all(1e-6 < v < 9.999999 for v in (p.X, p.Y, p.Z)):
                node = candidate
                break
        assert node is not None, "No interior node found"
    finally:
        labels.Dispose()
    point = node.Coordinates
    old = [point.X, point.Y, point.Z]
    mark = session.SetUndoMark(
        nx.Session.MarkVisibility.Visible, "NX MCP isolated mesh guard mutation"
    )
    try:
        builder = fem.BaseFEModel.NodeElementMgr.CreateNodeModifyLocationBuilder()
        try:
            builder.Node.Add([node])
            builder.XOption = True
            builder.YOption = False
            builder.ZOption = False
            assert builder.X.Units.Name == "MilliMeter"
            builder.X.RightHandSide = str(old[0] + 0.01)
            builder.Commit()
        finally:
            builder.Destroy()
        after = mesh_state.capture(fem)
        assert (
            before["counts"] == after["counts"]
            and mesh_state.compare(before, after)["state"] == "changed"
        )
    except Exception:
        session.UndoToMark(mark, None)
        session.DeleteUndoMark(mark, None)
        raise
    original = native_launch.claim_launch_gate
    calls = []

    def fuse(store, job_id):
        if job_id != "mesh-guard-positive-r1":
            return original(store, job_id)
        calls.append(job_id)
        raise NXToolError(
            "NX_TEST_SOLVER_FUSE",
            "Test safety stop: mesh guard should have rejected before launch gate",
        )

    native_launch.claim_launch_gate = fuse
    executor._mesh_guard_probe = {
        "fem": fem,
        "sim": sim,
        "node_label": int(node.Label),
        "old_coordinates": old,
        "before": before,
        "original_fuse": original,
        "fuse": fuse,
        "fuse_calls": calls,
        "initial_flags": flags,
    }
    session.DeleteUndoMark(mark, None)
    result = {
        "before": before,
        "after": after,
        "node_label": int(node.Label),
        "old_coordinates": old,
        "new_coordinates": [node.Coordinates.X, node.Coordinates.Y, node.Coordinates.Z],
        "fuse_installed": True,
        "solver_launched": False,
        "restoration_required": True,
    }
    Path(r"Z:\nx-mcp-integration\simcenter-discovery\mesh-guard-armed.json").write_text(
        json.dumps(result, indent=2)
    )
    return result

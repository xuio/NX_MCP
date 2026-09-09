def run(executor):
    import importlib

    from nx_mcp.simcenter import mesh_state
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    importlib.reload(mesh_state)
    nx, session = executor.nxopen, executor.session
    fem = session.Parts.BaseWork
    assert type(fem).__name__ == "FemPart" and "U-sim-update-20260909-r1" in fem.FullPath
    before = mesh_state.capture(fem)
    flags = [(p.FullPath, bool(p.IsModified)) for p in session.Parts]
    nodes = fem.BaseFEModel.FenodeLabelMap
    try:
        node = nodes.GetNode(nodes.AskNextNodeLabel(0))
    finally:
        nodes.Dispose()
    old = node.Coordinates
    mark = session.SetUndoMark(
        nx.Session.MarkVisibility.Visible, "NX MCP node-coordinate fingerprint probe"
    )
    result = {
        "before": before,
        "before_coordinates": [old.X, old.Y, old.Z],
        "solver_launched": False,
    }
    try:
        builder = fem.BaseFEModel.NodeElementMgr.CreateNodeModifyLocationBuilder()
        try:
            builder.Node.Add([node])
            result["x_units"] = builder.X.Units.Name if builder.X.Units else None
            builder.XOption = True
            builder.YOption = False
            builder.ZOption = False
            builder.X.RightHandSide = str(old.X + 0.01)
            builder.Commit()
        finally:
            builder.Destroy()
        xyz = node.Coordinates
        result["after_coordinates"] = [xyz.X, xyz.Y, xyz.Z]
        assert abs(xyz.X - old.X - 0.01) < 1e-10 and xyz.Y == old.Y and xyz.Z == old.Z
        after = mesh_state.capture(fem)
        result["after"] = after
        result["comparison"] = mesh_state.compare(before, after)
        assert after["counts"] == before["counts"] and result["comparison"]["state"] == "changed"
        result["passed"] = True
    except Exception as error:
        result["passed"] = False
        result["error"] = {"message": str(error), "nx_code": getattr(error, "ErrorCode", None)}
    finally:
        session.UndoToMark(mark, None)
        session.DeleteUndoMark(mark, None)
    result["restored"] = mesh_state.capture(fem) == before
    result["flags_restored"] = flags == [(p.FullPath, bool(p.IsModified)) for p in session.Parts]
    return result

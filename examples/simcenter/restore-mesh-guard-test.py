def run(executor):
    from nx_mcp.simcenter import mesh_state, native_launch

    probe = getattr(executor, "_mesh_guard_probe", None)
    if probe is None:
        return {"armed": False, "restoration_required": False}
    # Restore the test hook even if subsequent geometry recovery fails.
    if native_launch.claim_launch_gate is probe["fuse"]:
        native_launch.claim_launch_gate = probe["original_fuse"]
    nx, session = executor.nxopen, executor.session
    fem, sim = probe["fem"], probe["sim"]
    executor._sim_activate(executor._reference(fem, "part", fem, "FEM")["id"])
    labels = fem.BaseFEModel.FenodeLabelMap
    try:
        node = labels.GetNode(probe["node_label"])
    finally:
        labels.Dispose()
    mark = session.SetUndoMark(
        nx.Session.MarkVisibility.Visible, "NX MCP restore isolated guard node"
    )
    try:
        builder = fem.BaseFEModel.NodeElementMgr.CreateNodeModifyLocationBuilder()
        try:
            builder.Node.Add([node])
            builder.XOption = True
            builder.YOption = False
            builder.ZOption = False
            builder.X.RightHandSide = str(probe["old_coordinates"][0])
            builder.Commit()
        finally:
            builder.Destroy()
        restored = mesh_state.capture(fem)
        assert restored == probe["before"], "Mesh fingerprint not restored"
    except Exception:
        session.UndoToMark(mark, None)
        session.DeleteUndoMark(mark, None)
        raise
    after = [(p.FullPath, bool(p.IsModified)) for p in session.Parts]
    changes = [
        {"before": a, "after": b}
        for a, b in zip(probe["initial_flags"], after, strict=True)
        if a != b
    ]
    assert all(c["after"][0] in {fem.FullPath, sim.FullPath} for c in changes)
    calls = list(probe["fuse_calls"])
    result = {
        "restored": True,
        "mesh_state": restored,
        "fuse_restored": native_launch.claim_launch_gate is probe["original_fuse"],
        "fuse_calls": calls,
        "solver_launched": False,
        "only_test_flags_changed": True,
        "changed_flags": changes,
        "fem_path": fem.FullPath,
        "sim_path": sim.FullPath,
        "save_test_documents_required": True,
    }
    executor._mesh_guard_probe = None
    return result

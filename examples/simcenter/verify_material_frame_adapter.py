"""Native frame compare-and-set/readback/rollback; load only the isolated CAD."""


def run(executor):
    from nx_mcp.simcenter.dependencies import inspect_direct
    from nx_mcp.simcenter.material_orientation import assign_frame
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    s = executor.session
    sim = s.Parts.BaseWork
    assert sim.FullPath.endswith("selector_one_r1.sim")
    fem = sim.FemPart
    deps = inspect_direct(s, sim, executor.workspace)
    for issue in deps["unresolved"]:
        expected = executor.workspace.resolve(
            "ui-benchmarks/orthotropic-rotated-20260908-r1/RotatedOrthoR1_cad_01.prt"
        )
        assert (
            issue["association"] == "AssociatedCadPart"
            and executor.workspace.resolve(issue["path"]) == expected
        )
        _, status = s.Parts.OpenBase(str(expected))
        try:
            assert status is None or status.NumberUnloadedParts == 0
        finally:
            if status:
                status.Dispose()
    assert not inspect_direct(s, sim, executor.workspace)["unresolved"]
    flags = {p.FullPath: bool(p.IsModified) for p in s.Parts}
    collector = fem.BaseFEModel.MeshManager.GetMeshCollectors()[0]
    table = collector.ElementPropertyTable.GetNamedPropertyTablePropertyValue(
        "Solid Property"
    ).PropertyTable
    old = table.GetCoordinateSystemPropertyValue("material orientation")
    kind = table.GetIntegerPropertyValue("material orientation type")
    mark = None
    try:
        _, readback, mark = assign_frame(
            s,
            executor.nxopen,
            fem,
            collector,
            origin_mm=[0, 0, 0],
            x_axis=[0, 1, 0],
            y_axis=[-1, 0, 0],
            expected_type=kind,
            expected_frame=old,
        )
    finally:
        if mark is not None:
            s.UndoToMark(mark, None)
            s.DeleteUndoMark(mark, None)
        executor._sim_activate(executor._reference(sim, "part", sim, "part")["id"])
    assert table.GetCoordinateSystemPropertyValue("material orientation") == old
    assert table.GetIntegerPropertyValue("material orientation type") == kind
    assert flags == {p.FullPath: bool(p.IsModified) for p in s.Parts}
    return {
        "frame_readback": readback,
        "rollback_verified": True,
        "flags_preserved": True,
        "dependencies_loaded": True,
    }

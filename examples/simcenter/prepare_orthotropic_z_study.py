"""Independent cyclic material-frame benchmark for the third conductivity axis."""


def run(executor):
    from nx_mcp.simcenter.dependencies import inspect_direct
    from nx_mcp.simcenter.material_orientation import assign_frame
    from nx_mcp.simcenter.solver_guard import require_solver_idle
    from nx_mcp.simcenter.variant_clone import execute_clone_plan
    from nx_mcp.simcenter.variant_plan import plan_variant

    require_solver_idle()
    s = executor.session
    source = s.Parts.BaseWork
    assert source.FullPath.endswith("rotated_ortho_solve_r1.sim")
    before = {p.FullPath: bool(p.IsModified) for p in s.Parts}
    plan = plan_variant(
        executor.workspace,
        inspect_direct(s, source, executor.workspace),
        folder="ui-benchmarks/orthotropic-z-20260908-r1",
        name="OrthoZR1",
        saved_snapshot=True,
        loaded_paths=list(before),
    )
    clone = execute_clone_plan(s, executor.workspace, plan)
    opened = executor._sim_open(plan["mapping"][0]["destination"])
    sim = s.Parts.BaseWork
    fem = sim.FemPart
    for row in inspect_direct(s, sim, executor.workspace)["unresolved"]:
        assert (
            row["association"] == "AssociatedCadPart"
            and row["path"] == plan["mapping"][2]["destination"]
        )
        _, status = s.Parts.OpenBase(row["path"])
        try:
            assert status is None or status.NumberUnloadedParts == 0
        finally:
            if status:
                status.Dispose()
    assert not inspect_direct(s, sim, executor.workspace)["unresolved"]
    collectors = fem.BaseFEModel.MeshManager.GetMeshCollectors()
    assert len(collectors) == 1
    table = (
        collectors[0]
        .ElementPropertyTable.GetNamedPropertyTablePropertyValue("Solid Property")
        .PropertyTable
    )
    _, frame, mark = assign_frame(
        s,
        executor.nxopen,
        fem,
        collectors[0],
        origin_mm=[0, 0, 0],
        x_axis=[0, 1, 0],
        y_axis=[0, 0, 1],
        expected_type=table.GetIntegerPropertyValue("material orientation type"),
        expected_frame=table.GetCoordinateSystemPropertyValue("material orientation"),
    )
    saved = executor._sim_save(executor._reference(fem, "part", fem, "part")["id"])
    executor._sim_activate(opened["document"]["id"])
    after = {p.FullPath: bool(p.IsModified) for p in s.Parts}
    assert all(after.get(path) == flag for path, flag in before.items())
    return {
        "clone": clone,
        "frame": frame,
        "saved": saved,
        "source_flags_preserved": True,
        "solver_launched": False,
    }

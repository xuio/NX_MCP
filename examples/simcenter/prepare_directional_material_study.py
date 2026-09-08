"""Create and inspect an independent copy of the saved conduction benchmark."""


def run(executor):
    from nx_mcp.simcenter.dependencies import inspect_direct
    from nx_mcp.simcenter.properties import read_properties
    from nx_mcp.simcenter.variant_clone import execute_clone_plan
    from nx_mcp.simcenter.variant_plan import plan_variant

    session = executor.session
    sim = next(
        p
        for p in session.Parts
        if p.FullPath.endswith(r"B-contact-context-20260908-r2\contact_context_r2.sim")
    )
    flags = {p.FullPath: bool(p.IsModified) for p in session.Parts}
    plan = plan_variant(
        executor.workspace,
        inspect_direct(session, sim, executor.workspace),
        folder="ui-benchmarks/orthotropic-conduction-20260908-r1",
        name="OrthotropicR1",
        saved_snapshot=True,
        loaded_paths=list(flags),
    )
    clone = execute_clone_plan(session, executor.workspace, plan)
    opened = executor._sim_open(plan["mapping"][0]["destination"])
    copy = session.Parts.BaseWork
    fem = copy.FemPart
    collectors = []
    for c in fem.BaseFEModel.MeshManager.GetMeshCollectors():
        item = {
            "name": c.Name,
            "type": c.CollectorNeutralType,
            "collector_properties": read_properties(c.ElementPropertyTable, executor.nxopen),
        }
        if c.CollectorNeutralType == "Solid":
            table = c.ElementPropertyTable.GetNamedPropertyTablePropertyValue(
                "Solid Property"
            ).PropertyTable
            item["solid_properties"] = read_properties(table, executor.nxopen)
            item["solid_table_type"] = type(table).__name__
        collectors.append(item)
    after = {p.FullPath: bool(p.IsModified) for p in session.Parts}
    assert all(after.get(path) == flag for path, flag in flags.items())
    return {
        "clone": clone,
        "opened": opened,
        "collectors": collectors,
        "original_flags_preserved": True,
        "solver_launched": False,
    }

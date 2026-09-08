"""Close/reopen only the saved isolated two-source SIM and check actual load persistence."""


def run(executor):
    import json

    import NXOpen as nx

    from nx_mcp.runtime import NXToolError
    from nx_mcp.simcenter.properties import read_properties
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    session = executor.session
    sim = session.Parts.BaseWork
    path = sim.FullPath
    if "scenario-multi-mcp-20260908-r1" not in path or sim.IsModified:
        raise ValueError("Expected the saved unmodified isolated multi-source SIM")
    other_flags = {p.FullPath: bool(p.IsModified) for p in session.Parts if p != sim}

    def inspect(part):
        rows = []
        target_tags = []
        for load in part.Simulation.Loads:
            value = next(
                p for p in read_properties(load.PropertyTable, nx) if p["name"] == "Heat Load"
            )
            _, targets = load.TargetSetManager.GetTargetSetMembers(0)
            assert len(targets) == 1 and targets[0].Obj.OwningPart == part
            target_tags.append(int(targets[0].Obj.Tag))
            rows.append(
                {
                    "name": load.Name,
                    "power_W": float(value["expression"]),
                    "provenance": json.loads(load.GetStringUserAttribute("NX_MCP_PROVENANCE", -1)),
                    "accounting": load.GetStringUserAttribute("NX_MCP_ENERGY_ACCOUNTING", -1),
                }
            )
        assert len(set(target_tags)) == len(target_tags) == 2
        rows.sort(key=lambda row: row["name"])
        assert [(r["name"], r["power_W"]) for r in rows] == [("CPU", 8.0), ("SSD", 2.0)]
        assert all(r["accounting"] == "internal_heat" for r in rows)
        return rows

    before = inspect(sim)
    load = list(sim.Simulation.Loads)[0]
    old_load_id = executor._reference(load, "simulation_load", sim, "load")["id"]
    old_part_id = executor._part_id(sim)
    sim.Close(nx.BasePart.CloseWholeTree.FalseValue, nx.BasePart.CloseModified.CloseModified, None)
    executor.objects.invalidate_part(old_part_id)
    reopened, status = session.Parts.OpenBaseDisplay(path)
    if status:
        status.Dispose()
    session.Parts.SetWork(reopened)
    after = inspect(reopened)
    assert before == after
    try:
        executor.objects.resolve(old_load_id, expected_kind="simulation_load")
    except NXToolError as error:
        stale = error.code
    else:
        raise AssertionError("Closed-part load reference must be rejected")
    assert {p.FullPath: bool(p.IsModified) for p in session.Parts if p != reopened} == other_flags
    return {
        "path": path,
        "loads": after,
        "total_internal_heat_W": sum(r["power_W"] for r in after),
        "provenance_preserved": True,
        "distinct_targets": 2,
        "stale_reference_rejection": stale,
        "other_part_flags_preserved": True,
        "reopened_modified": bool(reopened.IsModified),
        "solver_launched": False,
    }

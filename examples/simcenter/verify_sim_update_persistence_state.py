def run(executor):
    import json
    from pathlib import Path
    from types import SimpleNamespace

    from nx_mcp.simcenter.mesh_plan import mesh_counts
    from nx_mcp.simcenter.property_values import preserved_getter_state
    from nx_mcp.simcenter.thermal_state import capture_analysis_thermal_state, compare_thermal_state

    sim = executor.session.Parts.BaseWork
    assert type(sim).__name__ == "SimPart" and "U-sim-update-20260909-r1" in sim.FullPath
    expected = json.loads(
        Path(r"Z:\nx-mcp-integration\simcenter-discovery\sim-update-r2-progress.json").read_text()
    )["before_update_state"]
    flags = [(p.FullPath, bool(p.IsModified)) for p in executor.session.Parts]
    with preserved_getter_state(executor.nxopen):
        state = capture_analysis_thermal_state(sim)
    counts = {
        "fem": mesh_counts(sim.FemPart),
        "sim": mesh_counts(SimpleNamespace(BaseFEModel=sim.Simulation.Femodel)),
    }
    comparison = compare_thermal_state(expected, state)
    return {
        "passed": comparison["state"] == "matches" and counts["fem"] == counts["sim"],
        "comparison": comparison,
        "state": state,
        "counts": counts,
        "flags_unchanged": flags
        == [(p.FullPath, bool(p.IsModified)) for p in executor.session.Parts],
        "solver_launched": False,
    }

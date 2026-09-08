"""Verify saved independent refinement survives reopening and native quality checks."""


def run(executor):
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    session = executor.session
    sim = session.Parts.BaseWork
    expected = executor.workspace.resolve(
        "ui-benchmarks/D-independent-clone-export-20260908-r1/independent_export.sim"
    )
    if (
        executor.workspace.resolve(sim.FullPath) != expected
        or sim.IsModified
        or sim.FemPart.IsModified
    ):
        raise ValueError("Require the saved refined clone")
    flags = {p.FullPath: bool(p.IsModified) for p in session.Parts}
    old = executor._reference(sim, "part", sim, "part")["id"]
    closed = executor._sim_close(old)
    opened = executor._sim_open(str(expected))
    sim = session.Parts.BaseWork
    fem = sim.FemPart
    elements, nodes = fem.BaseFEModel.FeelementLabelMap, fem.BaseFEModel.FenodeLabelMap
    try:
        counts = {"elements": elements.NumElements, "nodes": nodes.NumNodes}
    finally:
        elements.Dispose()
        nodes.Dispose()
    assert counts == {"elements": 261589, "nodes": 98632}
    quality = executor._sim_mesh_quality(
        executor._reference(fem, "part", fem, "part")["id"], include_settings=True
    )
    return {
        "state": "reopened_and_inspected",
        "closed": closed,
        "document": opened["document"],
        "counts": counts,
        "quality": quality,
        "flags_preserved": flags == {p.FullPath: bool(p.IsModified) for p in session.Parts},
        "solver_launched": False,
        "results_stale": True,
    }

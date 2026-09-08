"""Create one isolated K=0 counterpart of the saved fine K=2 flow benchmark."""


def run(executor):
    import hashlib
    import shutil
    import NXOpen as nx
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    source = executor.workspace.resolve(
        r"D:\CAD\SIMCENTER_MCP_WORKSPACE\ui-benchmarks\F-auto-observer-20260908-r1\auto_flow_r1.sim"
    )
    target = executor.workspace.resolve(
        r"D:\CAD\SIMCENTER_MCP_WORKSPACE\ui-benchmarks\D-fine-k0-20260908-r1\fine_k0_r1.sim"
    )
    if target.parent.exists():
        raise ValueError("Variant directory already exists; inspect it instead of retrying")
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    before = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    target.parent.mkdir()
    shutil.copy2(source, target)
    opened = executor._sim_open(str(target))
    sim = executor.session.Parts.BaseWork
    assert sim.FullPath.casefold() == str(target).casefold()
    assert sim.Simulation.ActiveSolution.AnalysisType == "Flow"
    fem = sim.FemPart
    em, nm = fem.BaseFEModel.FeelementLabelMap, fem.BaseFEModel.FenodeLabelMap
    try:
        counts = {"elements": em.NumElements, "nodes": nm.NumNodes}
    finally:
        em.Dispose()
        nm.Dispose()
    assert counts == {"elements": 186765, "nodes": 71748}, counts
    opening = next(b for b in sim.Simulation.SimulationObjects if b.Name == "Duct Opening")
    table = opening.PropertyTable.GetNamedPropertyTablePropertyValue("Head Loss").PropertyTable
    old, unit = table.GetBaseScalarWithDataPropertyValue("Head Loss Coefficient")
    assert old == 2.0
    mark = executor.session.SetUndoMark(
        nx.Session.MarkVisibility.Visible, "K=0 isolated comparison"
    )
    try:
        table.SetBaseScalarWithDataPropertyValue("Head Loss Coefficient", 0.0, unit)
        actual, actual_unit = table.GetBaseScalarWithDataPropertyValue("Head Loss Coefficient")
        assert actual == 0.0 and actual_unit == unit
    except Exception:
        executor.session.UndoToMark(mark, None)
        executor.session.DeleteUndoMark(mark, None)
        raise
    saved = executor._sim_save(opened["document"]["id"])
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    after = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    assert all(after.get(path) == flag for path, flag in before.items())
    return {
        "path": str(target),
        "source_path": str(source),
        "source_sha256": source_hash,
        "mesh_counts": counts,
        "coefficient_before": old,
        "coefficient_after": actual,
        "saved": saved,
        "source_file_preserved": True,
        "existing_document_flags_preserved": True,
        "solver_launched": False,
        "comparison_status": "not_solved",
    }

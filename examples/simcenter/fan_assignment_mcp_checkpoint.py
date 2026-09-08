"""Toggle a disposable outer checkpoint around the public fan assignment test."""


def run(executor):
    from nx_mcp.simcenter.fan_boundary import binding

    session, nx = executor.session, executor.nxopen
    state = getattr(executor, "_fan_assignment_mcp_checkpoint", None)
    if state is not None:
        sim, inlet, before, fields, mark, work, display, flags = state
        session.UndoToMark(mark, None)
        session.DeleteUndoMark(mark, None)
        assert binding(inlet.PropertyTable) == before
        assert {f.Tag for f in sim.FieldManager.Fields} == fields
        _, status = session.Parts.SetDisplay(display, False, False)
        if status:
            status.Dispose()
        session.Parts.SetWork(work)
        assert {p.FullPath: bool(p.IsModified) for p in session.Parts} == flags
        del executor._fan_assignment_mcp_checkpoint
        return {
            "phase": "cleanup",
            "original_binding_restored": True,
            "field_inventory_restored": True,
            "document_flags_preserved": True,
        }
    sim = next(
        p
        for p in session.Parts
        if p.FullPath.endswith(r"F-input-export-20260908-r2\flow_input_r2.sim")
    )
    work, display = session.Parts.BaseWork, session.Parts.BaseDisplay
    flags = {p.FullPath: bool(p.IsModified) for p in session.Parts}
    _, status = session.Parts.SetDisplay(sim, False, False)
    if status:
        status.Dispose()
    session.Parts.SetWork(sim)
    inlet = next(b for b in sim.Simulation.SimulationObjects if b.Name == "Duct Inlet")
    before = binding(inlet.PropertyTable)
    fields = {f.Tag for f in sim.FieldManager.Fields}
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "Public fan assignment test")
    executor._fan_assignment_mcp_checkpoint = (
        sim,
        inlet,
        before,
        fields,
        mark,
        work,
        display,
        flags,
    )
    return {"phase": "prepared", "document_path": sim.FullPath}

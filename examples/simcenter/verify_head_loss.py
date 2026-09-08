"""Check reusable native head-loss adapter, then undo the isolated inlet change."""


def run(executor):
    import importlib

    from nx_mcp.simcenter import head_loss

    importlib.reload(head_loss)
    s = executor.session
    sim = s.Parts.BaseWork
    if type(sim).__name__ != "SimPart" or "D-cavity-documents-20260908-r2" not in sim.FullPath:
        raise ValueError("Isolated cavity required")
    boundary = next(b for b in sim.Simulation.SimulationObjects if b.Name == "Duct Inlet")
    before = {int(t.Tag) for t in sim.ModelingObjectPropertyTables}
    mark = s.SetUndoMark(executor.nxopen.Session.MarkVisibility.Visible, "Verify head loss adapter")
    try:
        result = head_loss.attach_head_loss(s, sim, boundary, "Disposable inlet loss", 2.0)
        result.pop("table")
        try:
            head_loss.attach_head_loss(s, sim, boundary, "Must not duplicate", 3.0)
        except Exception as exc:
            if getattr(exc, "code", None) != "NX_SIM_TABLE_EXISTS":
                raise
            result["duplicate_rejected"] = True
        else:
            raise RuntimeError("Existing assignment not rejected")
        return result
    finally:
        s.UndoToMark(mark, None)
        s.DeleteUndoMark(mark, None)
        if (
            before != {int(t.Tag) for t in sim.ModelingObjectPropertyTables}
            or boundary.PropertyTable.GetNamedPropertyTablePropertyValue("Head Loss") is not None
        ):
            raise RuntimeError("Head loss adapter probe rollback mismatch")

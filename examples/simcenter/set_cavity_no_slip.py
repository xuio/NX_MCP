def run(executor):
    import json
    from pathlib import Path

    s = executor.session
    sim = s.Parts.BaseWork
    if type(sim).__name__ != "SimPart" or "D-cavity-documents-20260908-r2" not in sim.FullPath:
        raise ValueError("Cavity SIM required")
    record = Path(sim.FullPath).parent / "wall-mode-02.json"
    if record.exists():
        return {"replayed": True, "receipt": json.loads(record.read_text())}
    table = sim.Simulation.ActiveSolution.PropertyTable.GetNamedPropertyTablePropertyValue(
        "Flow Surface Parameters"
    ).PropertyTable
    before = table.GetIntegerPropertyValue("Wall Treatment")
    if before != 1:
        raise ValueError("Expected tested slip setting")
    mark = s.SetUndoMark(
        executor.nxopen.Session.MarkVisibility.Visible, "Explicit cavity wall treatment"
    )
    try:
        table.SetIntegerPropertyValue("Wall Treatment", 0)
        if table.GetIntegerPropertyValue("Wall Treatment") != 0:
            raise ValueError("Wall mode readback mismatch")
        result = {
            "before": before,
            "after": 0,
            "mode_meaning": "pending solver log verification",
            "saved": False,
        }
        with record.open("x") as f:
            json.dump(result, f, indent=2)
        return result
    except Exception:
        s.UndoToMark(mark, None)
        s.DeleteUndoMark(mark, None)
        raise

def run(executor):
    import json
    from pathlib import Path

    s = executor.session
    sim = s.Parts.BaseWork
    if type(sim).__name__ != "SimPart" or "D-cavity-documents-20260908-r2" not in sim.FullPath:
        raise ValueError("Cavity SIM required")
    record = Path(sim.FullPath).parent / "opening-pressure-mode-01.json"
    if record.exists():
        return {"replayed": True, "receipt": json.loads(record.read_text())}
    objects = [b for b in sim.Simulation.SimulationObjects if b.Name == "Duct Opening"]
    if len(objects) != 1:
        raise ValueError("Expected one opening")
    table = objects[0].PropertyTable
    before = table.GetIntegerPropertyValue("Pressure")
    if before != 0:
        raise ValueError("Expected default pressure mode")
    mark = s.SetUndoMark(
        executor.nxopen.Session.MarkVisibility.Visible, "Verify specified opening pressure"
    )
    try:
        table.SetIntegerPropertyValue("Pressure", 1)
        actual = table.GetIntegerPropertyValue("Pressure")
        if actual != 1:
            raise ValueError("Pressure mode did not persist")
        result = {
            "before": before,
            "after": actual,
            "meaning": "candidate specified pressure; export verification pending",
            "saved": False,
        }
        with record.open("x") as f:
            json.dump(result, f, indent=2)
        return result
    except Exception:
        s.UndoToMark(mark, None)
        s.DeleteUndoMark(mark, None)
        raise

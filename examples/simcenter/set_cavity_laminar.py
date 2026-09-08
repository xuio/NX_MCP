def run(executor):
    import json
    from pathlib import Path

    s = executor.session
    sim = s.Parts.BaseWork
    if type(sim).__name__ != "SimPart" or "D-cavity-documents-20260908-r2" not in sim.FullPath:
        raise ValueError("Cavity SIM required")
    record = Path(sim.FullPath).parent / "laminar-mode-01.json"
    if record.exists():
        return {"replayed": True, "receipt": json.loads(record.read_text())}
    table = sim.Simulation.ActiveSolution.PropertyTable
    before = table.GetIntegerPropertyValue("Turbulence Model")
    if before != 2:
        raise ValueError("Expected previously logged mixing-length model")
    mark = s.SetUndoMark(
        executor.nxopen.Session.MarkVisibility.Visible, "Cavity laminar model test"
    )
    try:
        table.SetIntegerPropertyValue("Turbulence Model", 0)
        if table.GetIntegerPropertyValue("Turbulence Model") != 0:
            raise ValueError("Mode readback mismatch")
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

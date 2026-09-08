def run(executor):
    import json
    from pathlib import Path

    s = executor.session
    sim = s.Parts.BaseWork
    if "D-cavity-documents-20260908-r2" not in sim.FullPath or type(sim).__name__ != "SimPart":
        raise ValueError("Cavity SIM required")
    record = Path(sim.FullPath).parent / "steady-step-01.json"
    if record.exists():
        return {"replayed": True, "receipt": json.loads(record.read_text())}
    step = sim.Simulation.ActiveSolution.ActiveStep
    original = step.PropertyTable.GetIntegerPropertyValue("Solution Type")
    if original != 1:
        raise ValueError("Expected native transient default before change")
    mark = s.SetUndoMark(executor.nxopen.Session.MarkVisibility.Visible, "Cavity steady-state step")
    try:
        step.PropertyTable.SetIntegerPropertyValue("Solution Type", 0)
        actual = step.PropertyTable.GetIntegerPropertyValue("Solution Type")
        if actual != 0:
            raise ValueError("Step mode readback differs")
        result = {
            "before": original,
            "after": actual,
            "semantic_validation": "pending solver input export",
            "saved": False,
        }
        with record.open("x") as f:
            json.dump(result, f, indent=2)
        return result
    except Exception:
        s.UndoToMark(mark, None)
        s.DeleteUndoMark(mark, None)
        raise

"""Attach native Flow configuration to the reopened, meshed cavity SIM."""


def run(executor):
    import json
    from pathlib import Path

    from nx_mcp.simcenter.flow import attach_default_tables, create_initial_step

    s = executor.session
    sim = s.Parts.BaseWork
    if "D-cavity-documents-20260908-r2" not in sim.FullPath or type(sim).__name__ != "SimPart":
        raise ValueError("Requires reopened cavity SIM")
    record = Path(sim.FullPath).parent / "cavity-flow-setup-01.json"
    if record.exists():
        return {"replayed": True, "receipt": json.loads(record.read_text())}
    sol = sim.Simulation.ActiveSolution
    if sol.StepCount:
        raise ValueError("Inspect existing steps before retrying")
    mark = s.SetUndoMark(
        executor.nxopen.Session.MarkVisibility.Visible, "Prepare cavity Flow solution"
    )
    try:
        result = {
            "step": create_initial_step(s, sim, "Duct benchmark step"),
            "tables": attach_default_tables(s, sim, "Duct benchmark"),
            "solve_ready": False,
            "saved": False,
        }
        with record.open("x") as stream:
            json.dump(result, stream, indent=2)
        return result
    except Exception:
        s.UndoToMark(mark, None)
        s.DeleteUndoMark(mark, None)
        raise

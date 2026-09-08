"""Create a second unsolved solution only in the isolated conduction fixture."""


def run(executor):
    import NXOpen.CAE as cae

    session = executor.session
    sim = session.Parts.BaseWork
    if not sim.FullPath.endswith(r"A-thermal-export-20260908-r1\thermal_input_r1.sim"):
        raise ValueError("Isolated conduction SIM required")
    name = "MCP_SELECTION_PROBE"
    existing = [s for s in sim.Simulation.Solutions if s.Name == name]
    if existing:
        raise ValueError("Probe solution already exists; inspect rather than recreate")
    before = sim.Simulation.ActiveSolution
    mark = session.SetUndoMark(
        executor.nxopen.Session.MarkVisibility.Visible, "MCP solution selection fixture"
    )
    try:
        added = sim.Simulation.CreateSolution(
            "NX MULTIPHYSICS",
            "Thermal",
            "Thermal",
            name,
            cae.SimSimulation.AxisymAbstractionType.NotSet,
        )
        sim.Simulation.ActiveSolution = before
        if sim.Simulation.ActiveSolution != before:
            raise ValueError("Original active solution was not restored")
        return {
            "created": added.Name,
            "restored": before.Name,
            "saved": False,
            "solver_launched": False,
        }
    except Exception:
        session.UndoToMark(mark, None)
        session.DeleteUndoMark(mark, None)
        raise

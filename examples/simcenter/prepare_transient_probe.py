"""Add one thermal step to the unsolved selection probe; do not change Conduction."""


def run(executor):
    sim = executor.session.Parts.BaseWork
    if not sim.FullPath.endswith(r"A-thermal-export-20260908-r1\thermal_input_r1.sim"):
        raise ValueError("Isolated thermal SIM required")
    solution = next(s for s in sim.Simulation.Solutions if s.Name == "MCP_SELECTION_PROBE")
    if solution.StepCount:
        raise ValueError("Probe already has steps; inspect rather than repeat")
    previous = sim.Simulation.ActiveSolution
    mark = executor.session.SetUndoMark(
        executor.nxopen.Session.MarkVisibility.Visible, "MCP transient probe step"
    )
    try:
        step = solution.CreateStep(0, True, "Transient probe")
        sim.Simulation.ActiveSolution = previous
        return {
            "solution": solution.Name,
            "step": step.Name,
            "step_count": solution.StepCount,
            "active_solution": sim.Simulation.ActiveSolution.Name,
            "saved": False,
        }
    except Exception:
        executor.session.UndoToMark(mark, None)
        raise

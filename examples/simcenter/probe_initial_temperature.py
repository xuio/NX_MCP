def run(executor):
    import NXOpen as nx

    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    session = executor.session
    sim = session.Parts.BaseWork
    assert sim.FullPath.endswith("temperature_material_public_r1.sim"), sim.FullPath
    sol = sim.Simulation.ActiveSolution
    assert sol.SolverType == "NX MULTIPHYSICS" and sol.AnalysisType == "Thermal"
    table = sol.PropertyTable

    def state():
        value, unit = table.GetBaseScalarWithDataPropertyValue("Initial Temperature Value")
        return {
            "mode": table.GetIntegerPropertyValue("Thermal Initial Temperature"),
            "value": value,
            "units": unit.Name,
            "temperature_k": sim.UnitCollection.Convert(
                unit, sim.UnitCollection.FindObject("Kelvin"), value
            ),
        }

    before = state()
    flags = [(p.FullPath, bool(p.IsModified)) for p in session.Parts]
    mark = session.SetUndoMark(
        nx.Session.MarkVisibility.Visible, "NX MCP initial temperature probe"
    )
    attempts = []
    try:
        table.SetIntegerPropertyValue("Thermal Initial Temperature", 1)
        table.SetBaseScalarWithDataPropertyValue(
            "Initial Temperature Value", 313.15, sim.UnitCollection.FindObject("Kelvin")
        )
        attempts.append(state())
        table.SetIntegerPropertyValue("Thermal Initial Temperature", 0)
        attempts.append(state())
    finally:
        session.UndoToMark(mark, None)
        session.DeleteUndoMark(mark, None)
    return {
        "before": before,
        "attempts": attempts,
        "restored": state() == before,
        "flags_restored": flags == [(p.FullPath, bool(p.IsModified)) for p in session.Parts],
        "solver_launched": False,
    }

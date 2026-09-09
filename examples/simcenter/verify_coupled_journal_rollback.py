def run(executor):
    import shutil

    from nx_mcp.simcenter import coupled_setup, flow
    from nx_mcp.simcenter.input_export import export_flow_input
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    s = executor.session
    nx = executor.nxopen
    source = executor.workspace.resolve(
        "ui-benchmarks/E-journal-init-control-20260909-r1/control.sim"
    )
    root = executor.workspace.resolve("ui-benchmarks/E-journal-rollback-20260909-r1")
    if root.exists():
        raise ValueError("Test exists")
    root.mkdir()
    target = root / "rollback.sim"
    shutil.copy2(source, target)
    sim, status = s.Parts.OpenBaseDisplay(str(target))
    status.Dispose()
    s.Parts.SetWork(sim)
    before = coupled_setup.read_initialization(sim.Simulation.ActiveSolution.PropertyTable)
    original = coupled_setup.initialize

    def failed(table):
        original(table)
        raise RuntimeError("Injected failure after native initialization writes")

    coupled_setup.initialize = failed
    try:
        try:
            flow.configure_coupled_steady(s, sim, "unused")
        except RuntimeError as exc:
            if str(exc) != "Injected failure after native initialization writes":
                raise
        else:
            raise ValueError("Failure was swallowed")
    finally:
        coupled_setup.initialize = original
    after = coupled_setup.read_initialization(sim.Simulation.ActiveSolution.PropertyTable)
    if before != after:
        raise ValueError("Rollback differs")
    result = flow.configure_coupled_steady(s, sim, "unused")
    status = sim.Save(nx.BasePart.SaveComponents.FalseValue, nx.BasePart.CloseAfterSave.FalseValue)
    status.Dispose()
    sim.Close(nx.BasePart.CloseWholeTree.FalseValue, nx.BasePart.CloseModified.CloseModified, None)
    sim, status = s.Parts.OpenBaseDisplay(str(target))
    status.Dispose()
    s.Parts.SetWork(sim)
    reopened = coupled_setup.read_initialization(sim.Simulation.ActiveSolution.PropertyTable)
    if reopened != result["initialization"]:
        raise ValueError("Reopened setup differs")
    exported = export_flow_input(s, executor.workspace, sim)
    sim.ModelingViews.WorkView.Fit()
    sim.ModelingViews.WorkView.UpdateDisplay()
    return {
        "rollback_verified": True,
        "before": before,
        "reopened": reopened,
        "exported": exported,
        "solver_launched": False,
    }

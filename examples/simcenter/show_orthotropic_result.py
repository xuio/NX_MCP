"""Show the completed refined result in the active dedicated Simcenter UI."""


def run(executor):
    from nx_mcp.interactive import _host
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    session = executor.session
    sim = session.Parts.BaseWork
    expected = executor.workspace.resolve(
        "ui-benchmarks/orthotropic-solve-20260908-r1/orthotropic_solve_r1.sim"
    )
    if executor.workspace.resolve(sim.FullPath) != expected:
        raise ValueError("Expected the completed refined analysis")
    flags = {p.FullPath: bool(p.IsModified) for p in session.Parts}
    ref = executor._reference(sim, "part", sim, "part")["id"]
    result = executor._sim_show_temperature(ref, name="Orthotropic conduction - temperature (C)")
    session.ListingWindow.CloseWindow()
    sim.ModelingViews.WorkView.Fit()
    sim.ModelingViews.WorkView.UpdateDisplay()
    log = executor.workspace.resolve(
        "ui-benchmarks/orthotropic-solve-20260908-r1/orthotropic_solve_r1-Conduction.log"
    ).read_text(errors="replace")
    return {
        "native_log": log,
        "view": result,
        "ui": _host.status(),
        "displayed_part": session.Parts.BaseDisplay.FullPath,
        "flags_preserved": flags == {p.FullPath: bool(p.IsModified) for p in session.Parts},
        "solver_launched": False,
    }

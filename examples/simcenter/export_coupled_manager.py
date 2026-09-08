"""Documented solve-manager export experiment from installed NXOpen.xml; export only."""


def run(executor):
    import time

    import NXOpen.CAE as cae

    from nx_mcp.simcenter.solver_guard import require_solver_idle
    from nx_mcp.simcenter.solver_log import inspect_input_xml, inspect_solver_log

    require_solver_idle()
    sim = executor.session.Parts.BaseWork
    if "E-ambient-reopen-20260908-r1" not in sim.FullPath:
        raise ValueError("Activate the retained coupled development SIM")
    sid = executor._reference(sim, "part", sim, "SIM")["id"]
    root = executor.workspace.resolve("ui-benchmarks/E-manager-export-20260908-r1")
    if root.exists():
        raise ValueError("Inspect retained export directory; do not repeat")
    copied = executor._sim_save_as(sid, str(root / "coupled_manager_r1.sim"))
    import NXOpen as nx
    import NXOpen.UF as uf

    status = sim.Save(nx.BasePart.SaveComponents.FalseValue, nx.BasePart.CloseAfterSave.FalseValue)
    if status:
        status.Dispose()
    started = time.monotonic()
    error = None
    try:
        manager = cae.SimSolveManager.GetSimSolveManager(executor.session)
        prerequisites = manager.GetChainOfPrerequisites(sim.Simulation.ActiveSolution)
        counts = manager.SolveChainOfSolutions(
            [sim.Simulation.ActiveSolution],
            cae.SimSolutionSolveOption.WriteSolverInputFile,
            cae.SimSolutionSetupCheckOption.CompleteCheckAndOutputErrors,
            cae.SimSolutionSolveMode.Foreground,
        )
    except Exception as exc:
        error = {
            "type": type(exc).__name__,
            "nx_code": getattr(exc, "ErrorCode", None),
            "message": str(exc),
        }
    report_path = root / "setup-report.txt"
    uf.UFSession.GetUFSession().Ui.SaveListingWindow(str(report_path))
    report = report_path.read_text(errors="replace")
    report = report[report.rfind("          Solution Model Setup Check Error Summary") :]
    files = []
    for path in root.iterdir():
        row = {"name": path.name, "bytes": path.stat().st_size}
        if path.is_file() and path.stat().st_size < 8 * 1024 * 1024:
            if path.suffix.lower() == ".xml":
                row["input"] = inspect_input_xml(path.read_bytes())
                import shutil

                shutil.copyfile(
                    path, r"Z:\nx-mcp-integration\simcenter-discovery\coupled-manager-deck.xml"
                )
            if path.suffix.lower() == ".log":
                row["log"] = inspect_solver_log(path.read_text(errors="replace"))
        files.append(row)
    return {
        "copy": copied,
        "manager_counts": list(counts) if error is None else None,
        "prerequisites": [[s.Name for s in prerequisites[0]], list(prerequisites[1])]
        if error is None
        else None,
        "setup_report": report,
        "native_error": error,
        "files": files,
        "elapsed_seconds": time.monotonic() - started,
        "solver_launched": False,
        "numerical_acceptance": False,
        "boundary_conditions_complete": False,
    }

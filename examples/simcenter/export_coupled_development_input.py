"""Export-only native experiment; incomplete boundaries preclude solve acceptance."""


def run(executor):
    import time
    import NXOpen.CAE as cae
    from nx_mcp.simcenter.solver_guard import require_solver_idle
    from nx_mcp.simcenter.solver_log import inspect_input_xml, inspect_solver_log

    require_solver_idle()
    sim = executor.session.Parts.BaseWork
    if "E-development-20260908-r1" not in sim.FullPath:
        raise ValueError("Activate the retained coupled development SIM")
    sid = executor._reference(sim, "part", sim, "SIM")["id"]
    root = executor.workspace.resolve("ui-benchmarks/E-development-export-20260908-r1")
    if root.exists():
        raise ValueError("Inspect retained export directory; do not repeat")
    copied = executor._sim_save_as(sid, str(root / "coupled_development.sim"))
    started = time.monotonic()
    error = None
    try:
        sim.Simulation.ActiveSolution.Solve(
            cae.SimSolutionSolveOption.WriteSolverInputFile,
            cae.SimSolutionSetupCheckOption.CompleteCheckAndOutputErrors,
        )
    except Exception as exc:
        error = {
            "type": type(exc).__name__,
            "nx_code": getattr(exc, "ErrorCode", None),
            "message": str(exc),
        }
    files = []
    for path in root.iterdir():
        row = {"name": path.name, "bytes": path.stat().st_size}
        if path.is_file() and path.stat().st_size < 8 * 1024 * 1024:
            if path.suffix.lower() == ".xml":
                row["input"] = inspect_input_xml(path.read_bytes())
            if path.suffix.lower() == ".log":
                row["log"] = inspect_solver_log(path.read_text(errors="replace"))
        files.append(row)
    return {
        "copy": copied,
        "native_error": error,
        "files": files,
        "elapsed_seconds": time.monotonic() - started,
        "solver_launched": False,
        "numerical_acceptance": False,
        "boundary_conditions_complete": False,
    }

"""Bounded direct expression-binding experiment from installed NXOpen.xml; export only."""


def run(executor):
    import time

    import NXOpen.CAE as cae

    from nx_mcp.simcenter.solver_guard import require_solver_idle
    from nx_mcp.simcenter.solver_log import inspect_input_xml, inspect_solver_log

    require_solver_idle()
    sim = executor.session.Parts.BaseWork
    if "E-ambient-guard-20260908-r1" not in sim.FullPath:
        raise ValueError("Activate the retained coupled development SIM")
    sid = executor._reference(sim, "part", sim, "SIM")["id"]
    root = executor.workspace.resolve("ui-benchmarks/E-environment-expression-20260908-r1")
    if root.exists():
        raise ValueError("Inspect retained export directory; do not repeat")
    copied = executor._sim_save_as(sid, str(root / "coupled_expression_r1.sim"))
    import NXOpen as nx
    import NXOpen.UF as uf

    table = sim.Simulation.ActiveSolution.PropertyTable
    environment_mark = executor.session.SetUndoMark(
        nx.Session.MarkVisibility.Visible, "MCP explicit ambient wrappers"
    )
    try:
        for key, value, unit in [
            ("Fluid Temperature", 20.0, "Celsius"),
            ("Absolute Pressure", 101325.0, "PressurePascals"),
        ]:
            expr = sim.Expressions.CreateSystemNumberExpression(
                str(value), sim.UnitCollection.FindObject(unit)
            )
            table.SetScalarPropertyValue(key, expr)
            actual_expression = table.GetScalarPropertyValue(key)
            assert actual_expression == expr
            actual_value, actual_unit = table.GetScalarWithDataPropertyValue(key)
            assert actual_value == value and actual_unit.Name == unit
        table.SetIntegerPropertyValue("Ambient Pressure", 1)
        assert table.GetIntegerPropertyValue("Ambient Pressure") == 1
    except Exception:
        executor.session.UndoToMark(environment_mark, None)
        raise
    step = sim.Simulation.ActiveSolution.ActiveStep
    old = step.PropertyTable.GetIntegerPropertyValue("Solution Type")
    mark = executor.session.SetUndoMark(
        nx.Session.MarkVisibility.Visible, "MCP coupled steady step"
    )
    try:
        step.PropertyTable.SetIntegerPropertyValue("Solution Type", 0)
        actual = step.PropertyTable.GetIntegerPropertyValue("Solution Type")
        assert actual == 0
    except Exception:
        executor.session.UndoToMark(mark, None)
        raise
    status = sim.Save(nx.BasePart.SaveComponents.FalseValue, nx.BasePart.CloseAfterSave.FalseValue)
    if status:
        status.Dispose()
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
                    path, r"Z:\nx-mcp-integration\simcenter-discovery\coupled-expression-deck.xml"
                )
            if path.suffix.lower() == ".log":
                row["log"] = inspect_solver_log(path.read_text(errors="replace"))
        files.append(row)
    return {
        "copy": copied,
        "step_type": {
            "before": old,
            "after": actual,
            "interpretation": "steady hypothesis pending native export validation",
        },
        "setup_report": report,
        "native_error": error,
        "files": files,
        "elapsed_seconds": time.monotonic() - started,
        "solver_launched": False,
        "numerical_acceptance": False,
        "boundary_conditions_complete": False,
    }

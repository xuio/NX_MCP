"""Native Multiphysics thermal/flow export with readback and retained failure artifacts."""

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.solver_log import inspect_input_xml, inspect_solver_log
from nx_mcp.simcenter.solver_manifest import input_identity


def export_flow_input(session, workspace, sim):
    import NXOpen.CAE as cae

    if not isinstance(sim, cae.SimPart) or session.Parts.BaseWork != sim:
        raise NXToolError("NX_INVALID_ARGUMENT", "Activate the selected SIM before exporting")
    solution = sim.Simulation.ActiveSolution
    if (
        solution is None
        or solution.SolverType != "NX MULTIPHYSICS"
        or solution.AnalysisType not in ("Flow", "Thermal", "Coupled Thermal-Flow")
    ):
        raise NXToolError(
            "NX_SIM_UNSUPPORTED",
            "This adapter currently supports NX MULTIPHYSICS Thermal, Flow and Coupled Thermal-Flow input export",
        )
    source = workspace.resolve(sim.FullPath)
    directory = source.parent
    if not source.is_file() or directory == workspace.root:
        raise NXToolError(
            "NX_INVALID_ARGUMENT", "Save an isolated SIM in a dedicated workspace subfolder first"
        )
    # Native export writes auxiliary files too. Refuse a populated folder rather
    # than guessing a vendor filename convention or overwriting earlier results.
    before = list(directory.iterdir())
    if any(p != source for p in before):
        raise NXToolError(
            "NX_SIM_OUTPUT_CONFLICT",
            "Export requires a directory containing only this SIM; copy the SIM to a fresh folder first",
            details={"mutation_outcome": "not_started"},
        )
    try:
        ambient = None
        pressure_validation = None
        native_ambient = None
        native_pressure = None
        pressure_mode = None
        if solution.AnalysisType == "Coupled Thermal-Flow":
            value, unit = solution.PropertyTable.GetScalarWithDataPropertyValue("Fluid Temperature")
            native_ambient = (value, unit.Name if unit else None)
            pressure_mode = solution.PropertyTable.GetIntegerPropertyValue("Ambient Pressure")
            if pressure_mode == 0:
                import NXOpen as nx

                wrapper = solution.PropertyTable.GetScalarFieldWrapperPropertyValue(
                    "Absolute Pressure"
                )
                expression = wrapper.GetExpression() if wrapper is not None else None
                if (
                    expression is None
                    or wrapper.GetField() is not None
                    or expression.Units is None
                    or expression.Units.Name != "PressurePascals"
                ):
                    raise ValueError(
                        "Specified coupled pressure requires an expression-backed Pa value; field definitions/scales are unverified"
                    )
                native_pressure = expression.GetValueUsingUnits(
                    nx.Expression.UnitsOption.Expression
                )
        solution.Solve(
            cae.SimSolutionSolveOption.WriteSolverInputFile,
            cae.SimSolutionSetupCheckOption.CompleteCheckAndOutputErrors,
        )
        artifacts = [workspace.ensure_inside(p) for p in directory.iterdir() if p != source]
        decks = [p for p in artifacts if p.is_file() and p.suffix.lower() == ".xml"]
        if len(decks) != 1:
            raise ValueError("Native export did not produce exactly one inspectable XML input")
        if decks[0].stat().st_size > 64 * 1024 * 1024:
            raise ValueError("Native input exceeds the 64 MiB validation limit")
        raw = decks[0].read_bytes()
        validation = inspect_input_xml(raw)
        if validation["state"] != "well_formed" or not validation.get("mesh_counts", {}).get(
            "elements"
        ):
            raise ValueError("Native export has invalid input or no mesh elements")
        if native_ambient is not None:
            from nx_mcp.simcenter.coupled_input import (
                inspect_ambient_pressure,
                inspect_ambient_temperature,
            )

            ambient = inspect_ambient_temperature(raw, *native_ambient)
            if not ambient["matches"]:
                raise ValueError(
                    "Coupled ambient temperature differs between native readback and exported input"
                )
            pressure_validation = inspect_ambient_pressure(raw, pressure_mode, native_pressure)
            if not pressure_validation["matches"]:
                raise ValueError(
                    "Coupled specified pressure differs between native readback and exported input"
                )
        logs = []
        for path in artifacts:
            if path.is_file() and path.suffix.lower() == ".log":
                if path.stat().st_size > 8 * 1024 * 1024:
                    raise ValueError("Translator log exceeds the 8 MiB inspection limit")
                report = inspect_solver_log(path.read_text(errors="replace"))
                logs.append({"path": str(path), **report})
                if report["state"] == "failed":
                    raise ValueError("Native translator reported failure")
        return {
            "input_path": str(decks[0]),
            "input_identity": input_identity(raw),
            "validation": validation,
            "coupled_ambient_validation": ambient,
            "coupled_pressure_validation": pressure_validation,
            "artifacts": [
                {"path": str(p), "bytes": p.stat().st_size if p.is_file() else None}
                for p in artifacts
            ],
            "translator_reports": logs,
            "solver": solution.SolverType,
            "analysis_type": solution.AnalysisType,
            "solution": solution.Name,
            "source_sim": str(source),
            "source_modified": bool(sim.IsModified),
            "solver_launched": False,
            "solve_readiness": "not_established",
            "scope": "Native thermal/flow input export, not a solve or convergence check",
        }
    except Exception as error:
        raise NXToolError(
            "NX_SIM_EXPORT_FAILED",
            "Native input export failed verification; inspect retained artifacts before retrying",
            nx_code=getattr(error, "ErrorCode", None),
            details={
                "mutation_outcome": "partial",
                "reason": str(error),
                "retained_directory": str(directory),
                "automatic_cleanup": False,
                "coupled_ambient_validation": ambient,
                "coupled_pressure_validation": pressure_validation,
            },
        ) from error

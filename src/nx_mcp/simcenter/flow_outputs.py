"""Selected native flow diagnostic output toggles; isolated-study use pending acceptance."""

from nx_mcp.runtime import NXToolError

OUTPUTS = {"mass_fluxes": "Mass Fluxes", "surface_pressure": "Surface Pressure", "y_plus": "Y+"}


def configure_outputs(session, sim, *, mass_fluxes, surface_pressure, y_plus):
    """Caller excludes live solvers. Only the selected global output table is edited."""
    import NXOpen as nx

    requested = {"mass_fluxes": mass_fluxes, "surface_pressure": surface_pressure, "y_plus": y_plus}
    if any(type(v) is not bool for v in requested.values()):
        raise NXToolError("NX_INVALID_ARGUMENT", "Output flags must be explicit booleans")
    if session.Parts.BaseWork != sim:
        raise NXToolError("NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate the selected SIM")
    sol = sim.Simulation.ActiveSolution
    if (
        sol is None
        or sol.SolverType != "NX MULTIPHYSICS"
        or sol.AnalysisType != "Coupled Thermal-Flow"
        or sol.StepCount != 1
    ):
        raise NXToolError(
            "NX_SIM_SOLUTION_TYPE", "Requires a single-step Multiphysics Coupled Thermal-Flow SIM"
        )
    key = "Thermal-Flow Output Requests"
    step = sol.GetStepByIndex(0).PropertyTable
    # An explicit step override would prevent the global flags governing the run.
    if step.GetNamedPropertyTablePropertyValue(key) is not None:
        raise NXToolError("NX_SIM_UNSUPPORTED_CONFIGURATION", "Step output override must be absent")
    named = sol.PropertyTable.GetNamedPropertyTablePropertyValue(key)
    if named is None:
        raise NXToolError("NX_SIM_CONFIGURATION_MISSING", "Attach a global output request")
    table = named.PropertyTable
    if table.GetIntegerPropertyValue("Flow Entity") != 0:
        raise NXToolError(
            "NX_SIM_UNSUPPORTED_CONFIGURATION", "Requires existing all-flow entity selection (0)"
        )

    def read():
        values = {k: table.GetBooleanPropertyValue(name) for k, name in OUTPUTS.items()}
        if any(type(v) is not bool for v in values.values()):
            raise NXToolError(
                "NX_SIM_UNSUPPORTED_CONFIGURATION", "Native output properties must be boolean"
            )
        return values

    before = read()
    result = {
        "before": before,
        "actual": requested,
        "changed": before != requested,
        "saved": False,
        "solver_launched": False,
        "native_acceptance": "pending",
        "existing_results_regenerated": False,
        "flux_conservation_verified": False,
    }
    if before == requested:
        return result
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "NX MCP flow diagnostic outputs")
    try:
        for key, name in OUTPUTS.items():
            if requested[key] != before[key]:
                table.SetBooleanPropertyValue(name, requested[key])
        if session.UpdateManager.DoUpdate(mark):
            raise NXToolError("NX_SIM_UPDATE_FAILED", "Output update reported errors")
        actual = read()
        if actual != requested:
            raise NXToolError("NX_SIM_READBACK_MISMATCH", "Output flags differ after assignment")
        result["actual"] = actual
        return result
    except Exception as error:
        try:
            session.UndoToMark(mark, None)
            if read() != before:
                raise RuntimeError("Output flags differ after rollback")
            session.DeleteUndoMark(mark, None)
        except Exception as recovery:
            raise NXToolError(
                "NX_SIM_ROLLBACK_FAILED",
                "Output update rollback incomplete",
                details={
                    "operation_error": str(error),
                    "recovery_error": str(recovery),
                    "mutation_outcome": "partial",
                },
            ) from error
        raise

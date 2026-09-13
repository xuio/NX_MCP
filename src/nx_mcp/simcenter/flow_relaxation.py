"""Bounded steady-flow damping controls; native acceptance remains pending."""

import math

from nx_mcp.runtime import NXToolError

FACTORS = {
    "global_factor": "Global Relaxation Factor",
    "mass_factor": "Mass Relaxation Factor",
    "fluids_factor": "Fluids Relaxation Factor",
}


def configure_relaxation(session, sim, *, global_factor, mass_factor, fluids_factor):
    """Caller must guard live solvers; no save, export or solve occurs here."""
    import NXOpen as nx

    requested = {
        "global_factor": global_factor,
        "mass_factor": mass_factor,
        "fluids_factor": fluids_factor,
    }
    for value in requested.values():
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not 0 < value <= 1
        ):
            raise NXToolError("NX_INVALID_ARGUMENT", "Relaxation factors must be finite in (0, 1]")
    if session.Parts.BaseWork != sim:
        raise NXToolError("NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate the selected SIM")
    sol = sim.Simulation.ActiveSolution
    if (
        sol is None
        or sol.SolverType != "NX MULTIPHYSICS"
        or sol.AnalysisType not in ("Flow", "Coupled Thermal-Flow")
        or sol.StepCount != 1
        or sol.GetStepByIndex(0).PropertyTable.GetIntegerPropertyValue("Solution Type") != 0
    ):
        raise NXToolError("NX_SIM_SOLUTION_TYPE", "Requires a single steady Multiphysics flow step")
    named = sol.PropertyTable.GetNamedPropertyTablePropertyValue("Flow Solution Parameters")
    if named is None:
        raise NXToolError("NX_SIM_CONFIGURATION_MISSING", "Attach Flow Solution Parameters")
    table = named.PropertyTable

    def read():
        result = {}
        for key, name in FACTORS.items():
            value, unit = table.GetBaseScalarWithDataPropertyValue(name)
            if unit is not None or not math.isfinite(value) or not 0 < value <= 1:
                raise NXToolError(
                    "NX_SIM_UNSUPPORTED_CONFIGURATION",
                    "Existing factors must be dimensionless in (0, 1]",
                )
            result[key] = float(value)
        return result

    before = read()
    requested = {k: float(v) for k, v in requested.items()}
    result = {
        "before": before,
        "actual": requested,
        "changed": before != requested,
        "saved": False,
        "solver_launched": False,
        "native_acceptance": "pending",
        "numerical_validity": "not_established",
    }
    if before == requested:
        return result
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "NX MCP flow relaxation factors")
    try:
        for key, name in FACTORS.items():
            if before[key] != requested[key]:
                table.SetBaseScalarWithDataPropertyValue(name, requested[key], None)
        if session.UpdateManager.DoUpdate(mark):
            raise NXToolError("NX_SIM_UPDATE_FAILED", "Relaxation update reported errors")
        actual = read()
        if any(
            not math.isclose(actual[k], requested[k], rel_tol=1e-12, abs_tol=0) for k in FACTORS
        ):
            raise NXToolError(
                "NX_SIM_READBACK_MISMATCH", "Relaxation factors differ after assignment"
            )
        result["actual"] = actual
        return result
    except Exception as error:
        try:
            session.UndoToMark(mark, None)
            if read() != before:
                raise RuntimeError("Relaxation factors differ after rollback")
            session.DeleteUndoMark(mark, None)
        except Exception as recovery:
            raise NXToolError(
                "NX_SIM_ROLLBACK_FAILED",
                "Relaxation change failed with incomplete rollback",
                details={
                    "operation_error": str(error),
                    "recovery_error": str(recovery),
                    "mutation_outcome": "partial",
                },
            ) from error
        raise

"""Physical steady-flow relaxation step; internal pending native acceptance."""

import math

from nx_mcp.runtime import NXToolError

MODE = "Steady State - Relaxation Time Step"
STEP = "Time Step"


def configure_physical_step(session, sim, *, time_step_s):
    """Change the active physical relaxation step only, preserving solver modes.

    The caller must guard against active solvers. Local stepping and transient
    solutions are rejected. No save, export or solve is performed here.
    """
    import NXOpen as nx

    if (
        isinstance(time_step_s, bool)
        or not isinstance(time_step_s, (int, float))
        or not math.isfinite(time_step_s)
        or time_step_s <= 0
    ):
        raise NXToolError("NX_INVALID_ARGUMENT", "Use a finite positive time step in seconds")
    if session.Parts.BaseWork != sim:
        raise NXToolError("NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate the selected SIM")
    solution = sim.Simulation.ActiveSolution
    if (
        solution is None
        or solution.SolverType != "NX MULTIPHYSICS"
        or solution.AnalysisType not in ("Flow", "Coupled Thermal-Flow")
        or solution.StepCount != 1
        or solution.GetStepByIndex(0).PropertyTable.GetIntegerPropertyValue("Solution Type") != 0
    ):
        raise NXToolError("NX_SIM_SOLUTION_TYPE", "Requires a single steady Multiphysics flow step")
    named = solution.PropertyTable.GetNamedPropertyTablePropertyValue("Flow Solution Parameters")
    if named is None:
        raise NXToolError("NX_SIM_CONFIGURATION_MISSING", "Attach Flow Solution Parameters")
    table = named.PropertyTable
    seconds = sim.UnitCollection.FindObject("Second")

    def read():
        mode = table.GetIntegerPropertyValue(MODE)
        value, unit = table.GetBaseScalarWithDataPropertyValue(STEP)
        if mode != 0 or unit != seconds or not math.isfinite(value) or value <= 0:
            raise NXToolError(
                "NX_SIM_UNSUPPORTED_CONFIGURATION",
                "Requires existing physical stepping with a positive scalar stored in seconds",
            )
        return float(value)

    before = read()
    result = {
        "before_s": before,
        "actual_s": float(time_step_s),
        "changed": before != time_step_s,
        "mode": "physical",
        "saved": False,
        "solver_launched": False,
        "native_acceptance": "pending",
        "numerical_validity": "not_established",
    }
    if before == time_step_s:
        return result
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "NX MCP steady flow time step")
    try:
        table.SetBaseScalarWithDataPropertyValue(STEP, float(time_step_s), seconds)
        if session.UpdateManager.DoUpdate(mark):
            raise NXToolError("NX_SIM_UPDATE_FAILED", "Time step update reported errors")
        actual = read()
        if not math.isclose(actual, time_step_s, rel_tol=1e-12, abs_tol=0):
            raise NXToolError("NX_SIM_READBACK_MISMATCH", "Physical relaxation step differs")
        result["actual_s"] = actual
        return result
    except Exception as error:
        try:
            session.UndoToMark(mark, None)
            if read() != before:
                raise RuntimeError("Physical relaxation step differs after rollback")
            session.DeleteUndoMark(mark, None)
        except Exception as recovery:
            raise NXToolError(
                "NX_SIM_ROLLBACK_FAILED",
                "Time step change failed with incomplete rollback",
                details={
                    "operation_error": str(error),
                    "recovery_error": str(recovery),
                    "mutation_outcome": "partial",
                },
            ) from error
        raise

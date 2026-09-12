"""NX 2606 Flow convergence properties, discovered from installed native tables."""

import math

from nx_mcp.runtime import NXToolError


def _preflight_error(code, message):
    return NXToolError(code, message, details={"mutation_outcome": "not_started"})


def configure_convergence(
    session,
    sim,
    *,
    residual,
    flow_imbalance_fraction,
    iteration_limit,
    heat_imbalance_fraction=None,
):
    """Set RMS residual and flow imbalance criteria; do not save or launch a solve."""
    import NXOpen as nx

    for name, value in (
        ("residual", residual),
        ("flow_imbalance_fraction", flow_imbalance_fraction),
    ) + (
        ()
        if heat_imbalance_fraction is None
        else (("heat_imbalance_fraction", heat_imbalance_fraction),)
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not 0 < value < 1
        ):
            raise _preflight_error(
                "NX_INVALID_ARGUMENT", name + " must be a finite fraction in (0, 1)"
            )
    if type(iteration_limit) is not int or not 1 <= iteration_limit <= 100000:
        raise _preflight_error(
            "NX_INVALID_ARGUMENT", "iteration_limit must be an integer in 1..100000"
        )
    if session.Parts.BaseWork != sim:
        raise _preflight_error("NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate the selected SIM first")
    sol = sim.Simulation.ActiveSolution
    if (
        sol is None
        or sol.SolverType != "NX MULTIPHYSICS"
        or sol.AnalysisType not in ("Flow", "Coupled Thermal-Flow")
    ):
        raise _preflight_error(
            "NX_SIM_SOLUTION_TYPE", "Requires NX MULTIPHYSICS Flow or Coupled Thermal-Flow"
        )
    named = sol.PropertyTable.GetNamedPropertyTablePropertyValue("Flow Solution Parameters")
    if named is None:
        raise _preflight_error("NX_SIM_CONFIGURATION_MISSING", "Attach Flow parameter tables first")
    table = named.PropertyTable
    if table.GetIntegerPropertyValue("Convergence Criteria") != 1:
        raise _preflight_error(
            "NX_SIM_UNSUPPORTED_CONFIGURATION", "Requires the verified RMS convergence mode (1)"
        )
    scalars = ("Maximum Residuals", "Global Flow Imbalance Fraction")
    if heat_imbalance_fraction is not None:
        scalars += ("Global Heat Imbalance Fraction",)
    option = "Global Flow Imbalance Fraction Option"
    heat_option = "Global Heat Imbalance Fraction Option"
    limit = "3D Flow Steady State - Iteration Limit"
    values = [table.GetBaseScalarWithDataPropertyValue(k) for k in scalars]
    if any(unit is not None for _, unit in values):
        raise _preflight_error(
            "NX_SIM_UNIT_MISMATCH", "Convergence fractions must be dimensionless"
        )

    def read():
        values = {
            "residual": table.GetBaseScalarWithDataPropertyValue(scalars[0])[0],
            "flow_imbalance_fraction": table.GetBaseScalarWithDataPropertyValue(scalars[1])[0],
            "flow_imbalance_enabled": table.GetBooleanPropertyValue(option),
            "iteration_limit": table.GetIntegerPropertyValue(limit),
        }

        if heat_imbalance_fraction is not None:
            values.update(
                heat_imbalance_fraction=table.GetBaseScalarWithDataPropertyValue(scalars[2])[0],
                heat_imbalance_enabled=table.GetBooleanPropertyValue(heat_option),
            )
        return values

    before = read()
    requested = {
        "residual": float(residual),
        "flow_imbalance_fraction": float(flow_imbalance_fraction),
        "flow_imbalance_enabled": True,
        "iteration_limit": iteration_limit,
    }
    if heat_imbalance_fraction is not None:
        requested.update(
            heat_imbalance_fraction=float(heat_imbalance_fraction), heat_imbalance_enabled=True
        )
    if before == requested:
        return {
            "before": before,
            "actual": before,
            "changed": False,
            "saved": False,
            "prior_results_require_revalidation": False,
        }
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "NX MCP flow convergence")
    try:
        fractions = (residual, flow_imbalance_fraction) + (
            () if heat_imbalance_fraction is None else (heat_imbalance_fraction,)
        )
        for key, value in zip(scalars, fractions, strict=True):
            table.SetBaseScalarWithDataPropertyValue(key, float(value), None)
        table.SetBooleanPropertyValue(option, True)
        if heat_imbalance_fraction is not None:
            table.SetBooleanPropertyValue(heat_option, True)
        table.SetIntegerPropertyValue(limit, iteration_limit)
        actual = read()
        if actual != requested:
            raise NXToolError(
                "NX_SIM_READBACK_MISMATCH", "Convergence settings differ after assignment"
            )
        return {
            "before": before,
            "actual": actual,
            "changed": True,
            "saved": False,
            "prior_results_require_revalidation": True,
        }
    except Exception as error:
        try:
            session.UndoToMark(mark, None)
            if read() != before:
                raise RuntimeError("Convergence settings differ after rollback")
            session.DeleteUndoMark(mark, None)
        except Exception as recovery:
            raise NXToolError(
                "NX_SIM_ROLLBACK_FAILED",
                "Convergence configuration failed with incomplete rollback",
                details={
                    "operation_error": str(error),
                    "recovery_error": str(recovery),
                    "mutation_outcome": "partial",
                },
            ) from error
        raise

"""Explicit native steady thermal stopping controls; never infer Automatic semantics."""

import math

from nx_mcp.runtime import NXToolError

MODE = "Steady State - Convergence Criteria"
CHANGE = "Steady State - Maximum Temperature Change"
BALANCE = "Steady State - Heat Imbalance"
OPTION = "Heat Imbalance Option"
FRACTION = "Global Fraction"
LIMIT = "Thermal Steady State - Iteration Limit"


def validate(maximum_temperature_change_k, iteration_limit, relative_heat_balance):
    if (
        type(maximum_temperature_change_k) not in (int, float)
        or not math.isfinite(maximum_temperature_change_k)
        or maximum_temperature_change_k <= 0
    ):
        raise NXToolError(
            "NX_INVALID_ARGUMENT", "Maximum temperature change must be positive finite K"
        )
    if type(iteration_limit) is not int or not 1 <= iteration_limit <= 1000000:
        raise NXToolError("NX_INVALID_ARGUMENT", "Iteration limit must be an integer in 1..1000000")
    if relative_heat_balance is not None and (
        type(relative_heat_balance) not in (int, float)
        or not math.isfinite(relative_heat_balance)
        or not 0 < relative_heat_balance <= 1
    ):
        raise NXToolError(
            "NX_INVALID_ARGUMENT",
            "Relative heat balance must be None or a finite fraction in (0,1]",
        )


def read_controls(table):
    change, unit = table.GetBaseScalarWithDataPropertyValue(CHANGE)
    fraction, fraction_unit = table.GetBaseScalarWithDataPropertyValue(FRACTION)
    return {
        "mode": table.GetIntegerPropertyValue(MODE),
        "maximum_temperature_change": change,
        "temperature_unit": unit.Name if unit else None,
        "relative_heat_balance_enabled": table.GetBooleanPropertyValue(BALANCE),
        "heat_balance_option": table.GetIntegerPropertyValue(OPTION),
        "relative_fraction": fraction,
        "fraction_unit": fraction_unit.Name if fraction_unit else None,
        "iteration_limit": table.GetIntegerPropertyValue(LIMIT),
    }


def configure(
    session, sim, maximum_temperature_change_k, iteration_limit=10000, relative_heat_balance=None
):
    import NXOpen as nx

    from nx_mcp.simcenter.solver_guard import require_solver_idle

    validate(maximum_temperature_change_k, iteration_limit, relative_heat_balance)
    sol = sim.Simulation.ActiveSolution
    if (
        session.Parts.BaseWork != sim
        or sol is None
        or sol.SolverType != "NX MULTIPHYSICS"
        or sol.AnalysisType != "Thermal"
    ):
        raise NXToolError("NX_SIM_UNSUPPORTED", "Activate an NX MULTIPHYSICS Thermal SIM")
    if sol.StepCount < 1 or any(
        sol.GetStepByIndex(i).PropertyTable.GetIntegerPropertyValue("Solution Type") != 0
        for i in range(sol.StepCount)
    ):
        raise NXToolError(
            "NX_SIM_UNSUPPORTED", "Selected solution must contain steady thermal steps only"
        )
    owner = sol.PropertyTable.GetNamedPropertyTablePropertyValue("Thermal Parameters")
    if owner is None or owner.DescriptorType != "Thermal Parameters" or owner.OwningPart != sim:
        raise NXToolError(
            "NX_SIM_SELECTION_OWNER", "Selected solution needs its own Thermal Parameters table"
        )
    table = owner.PropertyTable
    before = read_controls(table)
    delta = sim.UnitCollection.FindObject("CelsiusDifference")
    _, fraction_unit = table.GetBaseScalarWithDataPropertyValue(FRACTION)
    require_solver_idle()
    mark = session.SetUndoMark(
        nx.Session.MarkVisibility.Visible, "NX MCP explicit steady thermal controls"
    )
    try:
        table.SetIntegerPropertyValue(MODE, 1)
        table.SetBaseScalarWithDataPropertyValue(CHANGE, float(maximum_temperature_change_k), delta)
        table.SetIntegerPropertyValue(LIMIT, iteration_limit)
        table.SetBooleanPropertyValue(BALANCE, relative_heat_balance is not None)
        if relative_heat_balance is not None:
            table.SetIntegerPropertyValue(OPTION, 0)
            table.SetBaseScalarWithDataPropertyValue(
                FRACTION, float(relative_heat_balance), fraction_unit
            )
        actual = read_controls(table)
        if (
            actual["mode"] != 1
            or actual["maximum_temperature_change"] != float(maximum_temperature_change_k)
            or actual["temperature_unit"] != delta.Name
            or actual["iteration_limit"] != iteration_limit
            or actual["relative_heat_balance_enabled"] != (relative_heat_balance is not None)
        ):
            raise NXToolError(
                "NX_SIM_READBACK_MISMATCH", "Committed steady controls differ from request"
            )
        if relative_heat_balance is not None and (
            actual["heat_balance_option"] != 0
            or actual["relative_fraction"] != relative_heat_balance
            or actual["fraction_unit"] != before["fraction_unit"]
        ):
            raise NXToolError(
                "NX_SIM_READBACK_MISMATCH", "Committed relative heat-balance selector/value differs"
            )
        if sol.PropertyTable.GetNamedPropertyTablePropertyValue("Thermal Parameters") != owner:
            raise NXToolError(
                "NX_SIM_READBACK_MISMATCH", "Active solution table association changed"
            )
        return {
            "table": owner,
            "before": before,
            "actual": actual,
            "maximum_temperature_change_k": float(maximum_temperature_change_k),
            "relative_heat_balance": relative_heat_balance,
            "iteration_limit": iteration_limit,
            "mode": "specified",
            "temperature_semantics": "temperature difference: one CelsiusDifference equals one kelvin",
            "saved": False,
            "solver_launched": False,
            "results_require_revalidation": True,
        }
    except Exception as error:
        cleanup = []
        try:
            session.UndoToMark(mark, None)
            if read_controls(table) != before:
                cleanup.append("Control readback differs after rollback")
            session.DeleteUndoMark(mark, None)
        except Exception as recovery:
            cleanup.append(str(recovery))
        raise NXToolError(
            "NX_SIM_RECOVERY_INCOMPLETE"
            if cleanup
            else getattr(error, "code", "NX_SIM_AUTHORING_FAILED"),
            "Steady thermal control update failed",
            nx_code=getattr(error, "nx_code", getattr(error, "ErrorCode", None)),
            details={
                "cause": str(error),
                "cleanup": cleanup,
                "mutation_outcome": "partial" if cleanup else "rolled_back",
            },
        ) from error

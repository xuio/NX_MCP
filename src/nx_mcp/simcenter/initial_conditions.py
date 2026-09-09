"""Documented Thermal solution initial-temperature selectors; no solver inference."""

import math

from nx_mcp.runtime import NXToolError

MODES = {"automatic": 0, "uniform": 1}


def validate(mode, temperature_k):
    if mode not in MODES:
        raise ValueError(
            "mode must be automatic or uniform; result/file hot-start is not supported"
        )
    if mode == "automatic":
        if temperature_k is not None:
            raise ValueError("temperature_k is inactive in automatic mode; omit it")
    elif (
        isinstance(temperature_k, bool)
        or not isinstance(temperature_k, (int, float))
        or not math.isfinite(temperature_k)
        or temperature_k < 0
    ):
        raise ValueError("uniform mode requires a finite absolute temperature_k >= 0")


def readback(sim, solution):
    table = solution.PropertyTable
    value, unit = table.GetBaseScalarWithDataPropertyValue("Initial Temperature Value")
    selector = table.GetIntegerPropertyValue("Thermal Initial Temperature")
    if unit is None or not math.isfinite(value):
        raise ValueError("Initial temperature lacks a finite unit-bearing native value")
    kelvin = sim.UnitCollection.Convert(unit, sim.UnitCollection.FindObject("Kelvin"), value)
    if not math.isfinite(kelvin) or kelvin < 0:
        raise ValueError("Native initial temperature is outside absolute-temperature range")
    return {
        "mode": next((name for name, number in MODES.items() if number == selector), "other"),
        "selector": selector,
        "stored_temperature": {"value": value, "units": unit.Name, "temperature_k": kelvin},
        "temperature_active": selector == 1,
    }


def configure(session, sim, mode, temperature_k=None):
    validate(mode, temperature_k)
    import NXOpen as nx
    import NXOpen.CAE as cae

    from nx_mcp.simcenter.solver_guard import require_solver_idle

    if not isinstance(sim, cae.SimPart) or session.Parts.BaseWork != sim:
        raise ValueError("Select the active work SIM document")
    solution = sim.Simulation.ActiveSolution
    if solution is None or (solution.SolverType, solution.AnalysisType) != (
        "NX MULTIPHYSICS",
        "Thermal",
    ):
        raise ValueError("Requires an active NX MULTIPHYSICS Thermal solution")
    require_solver_idle()
    before = readback(sim, solution)
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "NX MCP initial conditions")
    try:
        table = solution.PropertyTable
        table.SetIntegerPropertyValue("Thermal Initial Temperature", MODES[mode])
        if mode == "uniform":
            table.SetBaseScalarWithDataPropertyValue(
                "Initial Temperature Value",
                float(temperature_k),
                sim.UnitCollection.FindObject("Kelvin"),
            )
        actual = readback(sim, solution)
        if actual["mode"] != mode or (
            mode == "uniform"
            and not math.isclose(
                actual["stored_temperature"]["temperature_k"],
                temperature_k,
                rel_tol=1e-12,
                abs_tol=1e-10,
            )
        ):
            raise ValueError("Initial-condition request did not commit faithfully")
        return {
            "before": before,
            "initial_conditions": actual,
            "saved": False,
            "results_stale": True,
            "solver_launched": False,
            "numerical_acceptance": "not_established",
            "warnings": [
                "Automatic initialization is chosen by native Simcenter; the stored temperature is inactive."
            ]
            if mode == "automatic"
            else [],
        }
    except Exception as exc:
        outcome = "rolled_back"
        try:
            session.UndoToMark(mark, None)
            session.DeleteUndoMark(mark, None)
        except Exception:
            outcome = "partial"
        raise NXToolError(
            "NX_SIM_INITIAL_CONDITIONS_FAILED",
            str(exc),
            nx_code=getattr(exc, "ErrorCode", None),
            details={
                "mutation_outcome": outcome,
                "next_step": "Inspect the active solution initial conditions before retrying",
            },
        ) from exc

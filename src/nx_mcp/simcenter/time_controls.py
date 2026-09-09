"""Native transient step configuration, invoked only on the NX UI thread.

Callers own document selection, solver-job exclusion and stale-result tracking.
This adapter does not save, export, or launch a solver.
"""

import math

from nx_mcp.runtime import NXToolError


def validate_times(end_times_s, max_temperature_change_k, min_time_step_s):
    if not isinstance(end_times_s, (list, tuple)) or not 2 <= len(end_times_s) <= 200:
        raise ValueError("Supply between 2 and 200 absolute result times")
    for value in [*end_times_s, max_temperature_change_k, min_time_step_s]:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError("Times and temperature-change controls must be finite numbers")
    if end_times_s[0] != 0 or any(
        a >= b for a, b in zip(end_times_s, end_times_s[1:], strict=False)
    ):
        raise ValueError("Result times must start at zero and strictly increase")
    if max_temperature_change_k <= 0 or min_time_step_s <= 0:
        raise ValueError("Temperature change and minimum time step must be positive")
    if min_time_step_s > min(b - a for a, b in zip(end_times_s, end_times_s[1:], strict=False)):
        raise ValueError("Minimum integration step exceeds a requested time interval")


def configure_transient_steps(
    session, sim, end_times_s, *, max_temperature_change_k, min_time_step_s
):
    """Set transient steps, retaining the installed time-method default.

    Readback confirms native settings, not the integration intervals eventually
    chosen by the solver. Existing extra steps are rejected, never deleted.
    """
    from nx_mcp.simcenter.properties import read_properties

    validate_times(end_times_s, max_temperature_change_k, min_time_step_s)
    import NXOpen as nx
    import NXOpen.CAE as cae

    if not isinstance(sim, cae.SimPart) or session.Parts.BaseWork != sim:
        raise ValueError("The selected SIM must already be the work document")
    solution = sim.Simulation.ActiveSolution
    if solution is None or not 1 <= solution.StepCount <= len(end_times_s):
        raise ValueError("Select a thermal solution with no more steps than requested times")
    # Verify known thermal controls before creating any object or undo mark.
    for index in range(solution.StepCount):
        table = solution.GetStepByIndex(index).PropertyTable
        table.GetIntegerPropertyValue("Thermal Time Step Method")
        table.GetBaseScalarWithDataPropertyValue("Maximum Temperature Change")
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    seconds = sim.UnitCollection.FindObject("Second")
    delta = sim.UnitCollection.FindObject("CelsiusDifference")
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "NX MCP transient time controls")
    try:
        steps = [solution.GetStepByIndex(i) for i in range(solution.StepCount)]
        while len(steps) < len(end_times_s):
            steps.append(solution.CreateStep(0, True, f"Transient sample {len(steps)}"))
        rows = []
        for index, (step, time) in enumerate(zip(steps, end_times_s, strict=True)):
            table = step.PropertyTable
            table.SetIntegerPropertyValue("Solution Type", 1)
            table.SetIntegerPropertyValue("Output Flag", 1)
            requested = {
                "End Time": (time, seconds),
                "Maximum Temperature Change": (max_temperature_change_k, delta),
                "Minimum Time Step": (min_time_step_s, seconds),
            }
            for key, (value, unit) in requested.items():
                table.SetBaseScalarWithDataPropertyValue(key, float(value), unit)
            actual = read_properties(table, nx)
            by_name = {p["name"]: p for p in actual}
            for key, (value, unit) in requested.items():
                row = by_name[key]
                if row.get("units") != unit.Name or not math.isclose(
                    row.get("value", math.nan), value, rel_tol=1e-12, abs_tol=1e-12
                ):
                    raise ValueError(f"Committed time control differs from request: {key}")
            if (
                by_name["Solution Type"].get("value") != 1
                or by_name["Output Flag"].get("value") != 1
            ):
                raise ValueError("Transient solution type or output flag did not commit")
            rows.append({"index": index, "name": step.Name, "properties": actual})
        return {
            "steps": rows,
            "step_count": len(rows),
            "requested_output_times_s": list(end_times_s),
            "saved": False,
            "results_stale": True,
            "integration_steps": "not_verified_until_solver_log_readback",
            "control_effects": {
                "output_times": "native_steps_configured",
                "maximum_temperature_change": "stored_but_effect_not_verified",
                "minimum_time_step": "stored_but_effect_not_verified",
            },
            "warnings": [
                "Stored time controls may be inactive under the installed time method; "
                "do not treat their readback as enforced numerical bounds."
            ],
        }
    except Exception as exc:
        outcome = "rolled_back"
        try:
            session.UndoToMark(mark, None)
            session.DeleteUndoMark(mark, None)
        except Exception:
            outcome = "partial"
        raise NXToolError(
            "NX_SIM_TIME_CONTROLS_FAILED",
            str(exc),
            nx_code=getattr(exc, "ErrorCode", None),
            details={
                "mutation_outcome": outcome,
                "next_step": "Inspect solution steps before retrying; do not use previous results",
            },
        ) from exc

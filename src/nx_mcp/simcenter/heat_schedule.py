"""Time-table binding for single-body internal power; no solver interpretation."""

import math

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter import scalar_tables


def validate_samples(manifest, scale, end_times):
    if type(scale) not in (int, float) or not math.isfinite(scale) or scale < 0:
        raise NXToolError("NX_INVALID_ARGUMENT", "Scale must be finite and nonnegative")
    if manifest["axis"] != "time" or manifest["quantity"] != "power":
        raise NXToolError("NX_SIM_FIELD_TYPE", "Select a registered time-axis power table")
    samples = manifest["samples"]
    if any(y < 0 or not math.isfinite(y * scale) for _, y in samples):
        raise NXToolError(
            "NX_INVALID_ARGUMENT",
            "Internal heat samples must be nonnegative and remain finite after scaling",
        )
    if not end_times or any(not math.isfinite(t) or t < 0 for t in end_times):
        raise NXToolError(
            "NX_SIM_TIME_CONTROLS", "Require finite nonnegative native transient end times"
        )
    if samples[0][0] != 0 or samples[-1][0] < max(end_times):
        raise NXToolError(
            "NX_SIM_FIELD_COVERAGE",
            "Power table must cover zero through every configured transient end time",
        )
    return {
        "scale": float(scale),
        "samples_w": [[x, y * scale] for x, y in samples],
        "covered_end_times_s": end_times,
    }


def validate_binding(sim, field, scale):
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    inspected = scalar_tables.inspect(sim, field)
    solution = sim.Simulation.ActiveSolution
    if (
        solution is None
        or solution.SolverType != "NX MULTIPHYSICS"
        or solution.AnalysisType != "Thermal"
    ):
        raise NXToolError("NX_SIM_UNSUPPORTED", "Select an NX MULTIPHYSICS Thermal solution")
    times = []
    seconds = sim.UnitCollection.FindObject("Second")
    for i in range(solution.StepCount):
        properties = solution.GetStepByIndex(i).PropertyTable
        if properties.GetIntegerPropertyValue("Solution Type") != 1:
            raise NXToolError(
                "NX_SIM_TIME_CONTROLS", "Configure every selected solution step as transient first"
            )
        value, unit = properties.GetBaseScalarWithDataPropertyValue("End Time")
        times.append(sim.UnitCollection.Convert(unit, seconds, value))
    return {
        **validate_samples(inspected["manifest"], scale, times),
        "manifest_sha256": inspected["manifest_sha256"],
        "definition": inspected["manifest"],
        "interpolation": "linear",
        "outside_table": "undefined",
        "numerical_acceptance": "not_established",
    }


def verify_committed(sim, load, actual, schedule):
    definition = actual.get("field_definition", {})
    if (
        actual.get("field_scale") != schedule["scale"]
        or definition.get("kind") != "validated_scalar_table"
        or definition.get("manifest") != schedule["definition"]
        or load.Tag not in {b.Tag for b in sim.Simulation.ActiveSolution.GetBcs()}
    ):
        raise NXToolError(
            "NX_SIM_READBACK_MISMATCH",
            "Heat schedule, scale or solution membership changed during commit",
        )

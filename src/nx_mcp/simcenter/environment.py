"""Explicit coupled ambient properties; native material laws remain authoritative.

NX 2606 opencae Thermal-Flow solution descriptor specifies Ambient Pressure=0
for supplied absolute pressure, scalar fields for pressure/temperature and a
boolean Buoyancy selector. Gravity is a separate native load, not an ambient key.
"""

import math

from nx_mcp.runtime import NXToolError


def validate(temperature_c, pressure_pa, buoyancy):
    if (
        type(temperature_c) not in (int, float)
        or not math.isfinite(temperature_c)
        or temperature_c <= -273.15
    ):
        raise NXToolError(
            "NX_INVALID_ARGUMENT", "Ambient temperature must be finite Celsius above absolute zero"
        )
    if type(pressure_pa) not in (int, float) or not math.isfinite(pressure_pa) or pressure_pa <= 0:
        raise NXToolError(
            "NX_INVALID_ARGUMENT", "Ambient absolute pressure must be positive finite Pa"
        )
    if type(buoyancy) is not bool:
        raise NXToolError("NX_INVALID_ARGUMENT", "buoyancy must be boolean")


def read(table):
    values = {}
    for key in ("Fluid Temperature", "Absolute Pressure"):
        value, unit = table.GetScalarWithDataPropertyValue(key)
        wrapper = table.GetScalarFieldWrapperPropertyValue(key)
        values[key] = {
            "value": value,
            "unit": unit.Name if unit else None,
            "scale": wrapper.GetFieldScaleFactor() if wrapper else None,
        }
    return {
        "ambient_pressure_selector": table.GetIntegerPropertyValue("Ambient Pressure"),
        "buoyancy": table.GetBooleanPropertyValue("Buoyancy"),
        "values": values,
    }


def configure(session, sim, temperature_c, pressure_pa, buoyancy):
    import NXOpen as nx
    import NXOpen.CAE as cae

    from nx_mcp.simcenter.coupled_setup import SOLUTION_UNITS, read_initialization
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    validate(temperature_c, pressure_pa, buoyancy)
    if not isinstance(sim, cae.SimPart) or session.Parts.BaseWork != sim:
        raise NXToolError("NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate the SIM")
    solution = sim.Simulation.ActiveSolution
    if (
        solution is None
        or solution.SolverType != "NX MULTIPHYSICS"
        or solution.AnalysisType != "Coupled Thermal-Flow"
    ):
        raise NXToolError("NX_SIM_SOLUTION_TYPE", "Requires NX MULTIPHYSICS Coupled Thermal-Flow")
    table = solution.PropertyTable
    if read_initialization(table) != {"solver_type": 6, "units": SOLUTION_UNITS}:
        raise NXToolError(
            "NX_SIM_PRECONDITION",
            "Initialize solution using nx_sim_flow_setup(action='coupled_steady') first",
        )
    require_solver_idle()
    before = read(table)
    expressions = sorted(int(e.Tag) for e in sim.Expressions)
    mark = session.SetUndoMark(
        nx.Session.MarkVisibility.Visible, "NX MCP explicit coupled environment"
    )
    try:
        for key, value, unit in (
            ("Fluid Temperature", temperature_c, "Celsius"),
            ("Absolute Pressure", pressure_pa, "PressurePascals"),
        ):
            expression = sim.Expressions.CreateSystemNumberExpression(
                str(float(value)), sim.UnitCollection.FindObject(unit)
            )
            wrapper = sim.FieldManager.CreateScalarFieldWrapperWithExpression(expression)
            table.SetScalarFieldWrapperPropertyValue(key, wrapper)
        table.SetIntegerPropertyValue("Ambient Pressure", 0)
        table.SetBooleanPropertyValue("Buoyancy", buoyancy)
        actual = read(table)
        if actual["ambient_pressure_selector"] != 0 or actual["buoyancy"] != buoyancy:
            raise NXToolError("NX_SIM_READBACK_MISMATCH", "Environment selector differs")
        for key, value, unit in (
            ("Fluid Temperature", temperature_c, "Celsius"),
            ("Absolute Pressure", pressure_pa, "PressurePascals"),
        ):
            row = actual["values"][key]
            if (
                row["unit"] != unit
                or not math.isclose(row["value"], value, rel_tol=1e-12, abs_tol=1e-12)
                or row["scale"] != 1.0
            ):
                raise NXToolError(
                    "NX_SIM_READBACK_MISMATCH", "Environment scalar, scale or unit differs"
                )
        return {
            "previous": before,
            "actual": actual,
            "temperature_c": temperature_c,
            "pressure_pa": pressure_pa,
            "pressure_mode": "specified_absolute",
            "density_treatment": "assigned native material law; altitude-derived ambient pressure disabled",
            "gravity": "existing native gravity loads unchanged; inspect before buoyant solve",
            "saved": False,
            "results_stale": True,
            "solver_launched": False,
        }
    except Exception as error:
        try:
            session.UndoToMark(mark, None)
            if read(table) != before or sorted(int(e.Tag) for e in sim.Expressions) != expressions:
                raise RuntimeError("Environment rollback readback differs")
            session.DeleteUndoMark(mark, None)
        except Exception as recovery:
            raise NXToolError(
                "NX_SIM_RECOVERY_INCOMPLETE",
                "Environment rollback failed",
                details={"mutation_outcome": "partial", "recovery_error": str(recovery)},
            ) from error
        raise NXToolError(
            "NX_SIM_AUTHORING_FAILED",
            "Environment configuration failed and was rolled back",
            nx_code=getattr(error, "nx_code", getattr(error, "ErrorCode", None)),
            details={"mutation_outcome": "rolled_back"},
        ) from error

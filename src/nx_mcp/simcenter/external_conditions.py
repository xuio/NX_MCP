"""Documented NX 2606 explicit external temperature on inlet/opening boundaries."""

import math

from nx_mcp.runtime import NXToolError


def assign_external_temperature(session, sim, boundaries, name, temperature_c):
    import NXOpen as nx

    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    solution = sim.Simulation.ActiveSolution
    if (
        session.Parts.BaseWork != sim
        or solution.AnalysisType != "Coupled Thermal-Flow"
        or solution.SolverType != "NX MULTIPHYSICS"
    ):
        raise NXToolError(
            "NX_SIM_SOLUTION_TYPE", "Activate an NX MULTIPHYSICS Coupled Thermal-Flow SIM"
        )
    if (
        type(temperature_c) not in (int, float)
        or not math.isfinite(temperature_c)
        or temperature_c <= -273.15
    ):
        raise NXToolError(
            "NX_INVALID_ARGUMENT", "Temperature must be finite Celsius above absolute zero"
        )
    if not isinstance(name, str) or not name.strip():
        raise NXToolError("NX_INVALID_ARGUMENT", "Supply a nonempty conditions name")
    if (
        not boundaries
        or len(boundaries) > 100
        or len({int(b.Tag) for b in boundaries}) != len(boundaries)
    ):
        raise NXToolError("NX_INVALID_ARGUMENT", "Select 1..100 distinct inlet/opening references")
    owned = list(sim.Simulation.SimulationObjects)
    if any(
        b.OwningPart != sim or b not in owned or b.DescriptorName not in ("Inlet", "Opening")
        for b in boundaries
    ):
        raise NXToolError(
            "NX_SIM_SELECTION_OWNER", "Select Inlet or Opening objects owned by this SIM"
        )
    tables = sim.ModelingObjectPropertyTables
    if any(t.Name.casefold() == name.casefold() for t in tables):
        raise NXToolError("NX_SIM_NAME_CONFLICT", "Conditions name already exists")
    key = "Inlet Conditions"
    if any(b.PropertyTable.GetNamedPropertyTablePropertyValue(key) is not None for b in boundaries):
        raise NXToolError(
            "NX_SIM_TABLE_EXISTS",
            "Explicit external conditions already assigned; inspect before editing",
        )
    before = {int(t.Tag) for t in tables}
    mark = session.SetUndoMark(
        nx.Session.MarkVisibility.Visible, "MCP explicit external temperature"
    )
    try:
        table = tables.CreateModelingObjectPropertyTable(
            "External Conditions",
            "NX MULTIPHYSICS - Coupled Thermal-Flow",
            "NX MULTIPHYSICS",
            name,
            0,
        )
        props = table.PropertyTable
        props.SetIntegerPropertyValue("Temperature Option", 0)
        expression = sim.Expressions.CreateSystemNumberExpression(
            str(float(temperature_c)), sim.UnitCollection.FindObject("Celsius")
        )
        wrapper = sim.FieldManager.CreateScalarFieldWrapperWithExpression(expression)
        props.SetScalarFieldWrapperPropertyValue("Temperature Value", wrapper)
        for boundary in boundaries:
            boundary.PropertyTable.SetNamedPropertyTablePropertyValue(key, table)
        value, unit = props.GetScalarWithDataPropertyValue("Temperature Value")
        if (
            value != temperature_c
            or unit.Name != "Celsius"
            or props.GetIntegerPropertyValue("Temperature Option") != 0
            or any(
                b.PropertyTable.GetNamedPropertyTablePropertyValue(key) != table for b in boundaries
            )
        ):
            raise NXToolError(
                "NX_SIM_READBACK_MISMATCH", "External conditions did not match after assignment"
            )
        return {
            "table": table,
            "temperature_c": value,
            "temperature_mode": "specified",
            "boundary_count": len(boundaries),
            "saved": False,
            "results_stale": True,
            "global_ambient_changed": False,
            "solver_launched": False,
        }
    except Exception as error:
        try:
            session.UndoToMark(mark, None)
            if {int(t.Tag) for t in tables} != before or any(
                b.PropertyTable.GetNamedPropertyTablePropertyValue(key) is not None
                for b in boundaries
            ):
                raise RuntimeError("External conditions rollback did not restore bindings/tables")
            session.DeleteUndoMark(mark, None)
        except Exception as recovery:
            raise NXToolError(
                "NX_SIM_ROLLBACK_FAILED",
                "External temperature assignment failed with incomplete recovery",
                details={"mutation_outcome": "partial", "recovery_error": str(recovery)},
            ) from error
        raise NXToolError(
            getattr(error, "code", "NX_SIM_AUTHORING_FAILED"),
            "External temperature assignment failed and rolled back",
            nx_code=getattr(error, "ErrorCode", None),
            details={"mutation_outcome": "rolled_back"},
        ) from error

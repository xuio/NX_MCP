"""NX 2606 static fan-curve assignment to an existing Flow or coupled inlet."""

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.fan_field import inspect_fan_table


def binding(properties):
    wrapper = properties.GetScalarFieldWrapperPropertyValue("Fan Curve")
    return {
        "mode": properties.GetIntegerPropertyValue("Mode Option"),
        "field_tag": int(wrapper.GetField().Tag) if wrapper and wrapper.GetField() else None,
        "scale_factor": wrapper.GetFieldScaleFactor() if wrapper else None,
    }


def assign_static_fan(session, sim, inlet, table):
    """Assign a verified table at scale one; preserve all other inlet properties.

    No orientation, reference pressure, motor heat or solver settings are inferred.
    A host-wide process snapshot excludes known running solvers. Coupled authoring is verified separately from coupled export/numerical
    acceptance. Total-pressure routes are not validated by this adapter.
    """
    import NXOpen as nx
    import NXOpen.CAE as cae

    if not isinstance(sim, cae.SimPart) or session.Parts.BaseWork != sim:
        raise NXToolError("NX_SIM_DOCUMENT_NOT_ACTIVE", "Activate the selected SIM")
    solution = sim.Simulation.ActiveSolution
    if (
        solution is None
        or solution.SolverType != "NX MULTIPHYSICS"
        or solution.AnalysisType not in ("Flow", "Coupled Thermal-Flow")
    ):
        raise NXToolError(
            "NX_SIM_SOLUTION_TYPE", "Select NX MULTIPHYSICS Flow or Coupled Thermal-Flow"
        )
    if (
        inlet.OwningPart != sim
        or inlet not in list(sim.Simulation.SimulationObjects)
        or inlet.DescriptorName != "Inlet"
    ):
        raise NXToolError("NX_SIM_SELECTION_OWNER", "Select an Inlet owned by this SIM")
    audit = inspect_fan_table(sim, table)
    if audit["manifest"]["pressure_convention"] != "static":
        raise NXToolError(
            "NX_SIM_UNSUPPORTED", "Only static-pressure fan inlet semantics are verified"
        )
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    solver_preflight = require_solver_idle()
    properties = inlet.PropertyTable
    before = binding(properties)
    inventory = ({f.Tag for f in sim.FieldManager.Fields}, {e.Tag for e in sim.Expressions})
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "NX MCP assign static fan inlet")
    try:
        wrapper = sim.FieldManager.CreateScalarFieldWrapperWithField(table, 1.0)
        properties.SetScalarFieldWrapperPropertyValue("Fan Curve", wrapper)
        properties.SetIntegerPropertyValue("Mode Option", 5)
        actual = binding(properties)
        if actual != {"mode": 5, "field_tag": int(table.Tag), "scale_factor": 1.0}:
            raise NXToolError("NX_SIM_READBACK_MISMATCH", "Fan inlet assignment differs")
        return {
            "solver_preflight": solver_preflight,
            "analysis_type": solution.AnalysisType,
            "numerical_acceptance": False,
            "binding": actual,
            "previous_binding": before,
            "manifest": audit["manifest"],
            "results_stale": True,
            "saved": False,
            "orientation": "existing inlet definition; unchanged",
            "pressure_reference": "existing inlet and solution values; unchanged",
            "motor_heat": "not_assigned",
            "operating_point": "requires solve",
        }
    except Exception as error:
        try:
            session.UndoToMark(mark, None)
            if binding(properties) != before or inventory != (
                {f.Tag for f in sim.FieldManager.Fields},
                {e.Tag for e in sim.Expressions},
            ):
                raise RuntimeError("Fan binding or inventory was not restored")
            session.DeleteUndoMark(mark, None)
        except Exception as recovery:
            raise NXToolError(
                "NX_SIM_RECOVERY_INCOMPLETE",
                "Fan assignment rollback failed",
                details={"mutation_outcome": "partial", "recovery_error": str(recovery)},
            ) from error
        raise NXToolError(
            getattr(error, "code", "NX_SIM_AUTHORING_FAILED"),
            "Fan assignment failed and was rolled back",
            nx_code=getattr(error, "ErrorCode", None),
            details={"mutation_outcome": "rolled_back"},
        ) from error

"""Guarded conversion of an existing constant-flow internal fan to a table."""

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.boundary_state import capture_effective_membership
from nx_mcp.simcenter.fan_field import inspect_fan_table
from nx_mcp.simcenter.internal_fan import snapshot
from nx_mcp.simcenter.internal_fan_edit import inspect
from nx_mcp.simcenter.properties import read_properties


def preserved(boundary, nx):
    _, members = boundary.TargetSetManager.GetTargetSetMembers(0)
    return {
        "name": boundary.Name,
        "targets": sorted((int(m.Obj.Tag), str(m.SubType), int(m.SubId)) for m in members),
        "properties": [p for p in read_properties(boundary.PropertyTable, nx)
                       if p["name"] not in ("Mode Option", "Fan Curve")],
    }


def assign(session, sim, boundary, table):
    import NXOpen as nx

    sol = sim.Simulation.ActiveSolution
    if (session.Parts.BaseWork != sim or sol is None
            or sol.SolverType != "NX MULTIPHYSICS"
            or sol.AnalysisType not in ("Flow", "Coupled Thermal-Flow")
            or sol.StepCount != 1 or list(sim.Simulation.Solutions) != [sol]):
        raise NXToolError("NX_SIM_SOLUTION_TYPE", "Activate a single-solution, single-step flow SIM")
    before = inspect(boundary, sim)
    audit = inspect_fan_table(sim, table)
    if audit["manifest"]["pressure_convention"] != "static":
        raise NXToolError("NX_SIM_UNSUPPORTED", "Requires an audited static-pressure fan table")
    membership = capture_effective_membership(sim)
    if not membership["comparison_verified"]:
        raise NXToolError("NX_SIM_UNSUPPORTED_CONFIGURATION", "Membership must be fully readable")
    kept = preserved(boundary, nx)
    inventory = snapshot(sim)
    old_wrapper = boundary.PropertyTable.GetScalarFieldWrapperPropertyValue("Fan Curve")
    old_wrapper_tag = int(old_wrapper.Tag) if old_wrapper else None
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "NX MCP Internal Fan curve")
    try:
        wrapper = sim.FieldManager.CreateScalarFieldWrapperWithField(table, 1.0)
        p = boundary.PropertyTable
        p.SetScalarFieldWrapperPropertyValue("Fan Curve", wrapper)
        p.SetIntegerPropertyValue("Mode Option", 4)
        if session.UpdateManager.DoUpdate(mark):
            raise NXToolError("NX_SIM_UPDATE_FAILED", "Fan curve update reported errors")
        actual = p.GetScalarFieldWrapperPropertyValue("Fan Curve")
        after = snapshot(sim)
        if (p.GetIntegerPropertyValue("Mode Option") != 4 or actual is None
                or actual.GetField() != table or actual.GetFieldScaleFactor() != 1.0
                or actual.GetExpression() is not None
                or preserved(boundary, nx) != kept
                or capture_effective_membership(sim) != membership
                or any(after[k] != inventory[k] for k in inventory if k != "modified")
                or inspect_fan_table(sim, table) != audit):
            raise NXToolError("NX_SIM_READBACK_MISMATCH", "Curve binding or preserved SIM state differs")
        return {"changed": True, "mode": "fan_curve", "previous_flow_m3_s": before["flow"],
                "fan_table_audit": audit, "preserved": kept, "membership_preserved": True,
                "saved": False, "solver_launched": False, "results_stale": True,
                "native_export_acceptance": "pending"}
    except Exception as error:
        try:
            session.UndoToMark(mark, None)
            restored = boundary.PropertyTable.GetScalarFieldWrapperPropertyValue("Fan Curve")
            restored_tag = int(restored.Tag) if restored else None
            if (inspect(boundary, sim) != before or preserved(boundary, nx) != kept
                    or restored_tag != old_wrapper_tag or snapshot(sim) != inventory
                    or capture_effective_membership(sim) != membership
                    or inspect_fan_table(sim, table) != audit):
                raise RuntimeError("Fan curve rollback differs")
            session.DeleteUndoMark(mark, None)
        except Exception as recovery:
            raise NXToolError("NX_SIM_ROLLBACK_FAILED", "Fan curve rollback incomplete",
                              details={"mutation_outcome": "partial", "operation_error": str(error),
                                       "recovery_error": str(recovery)}) from error
        raise NXToolError(getattr(error, "code", "NX_SIM_AUTHORING_FAILED"),
                          "Fan curve conversion failed and was rolled back",
                          details={"mutation_outcome": "rolled_back", "operation_error": str(error)}) from error

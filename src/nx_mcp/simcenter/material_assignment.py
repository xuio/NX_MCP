"""Explicit local solid material assignment with state binding and rollback."""

from nx_mcp.runtime import NXToolError
from nx_mcp.simcenter.collector_state import inspect_collector


def assign_material(session, nx, fem, collector, material, reference, expected_state_sha256):
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    if collector not in list(fem.BaseFEModel.MeshManager.GetMeshCollectors()):
        raise NXToolError("NX_SIM_SELECTION_OWNER", "Collector does not belong to this FEM")
    if material not in list(fem.MaterialManager.PhysicalMaterials):
        raise NXToolError("NX_SIM_SELECTION_OWNER", "Material must be local to this FEM")
    if collector.CollectorNeutralType != "Solid":
        raise NXToolError("NX_SIM_UNSUPPORTED", "Select a solid mesh collector")
    units = "mm" if fem.PartUnits == nx.BasePart.Units.Millimeters else "inch"
    before = inspect_collector(fem, collector, reference, units)
    if not before.get("state_sha256"):
        raise NXToolError("NX_SIM_READBACK_FAILED", "Cannot inspect current collector state")
    if before["state_sha256"] != expected_state_sha256:
        raise NXToolError("NX_SIM_REVISION_MISMATCH", "Collector changed; inspect it again")
    _, status = session.Parts.SetDisplay(fem, False, False)
    if status:
        status.Dispose()
    session.Parts.SetWork(fem)
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "NX MCP material assignment")
    try:
        table = collector.ElementPropertyTable.GetNamedPropertyTablePropertyValue(
            "Solid Property"
        ).PropertyTable
        options = fem.NewMaterialOptions()
        try:
            options.Material = material
            options.MaterialInherited = False
            table.SetPhysicalMaterialPropertyValue("material", options)
        finally:
            options.Dispose()
        after = inspect_collector(fem, collector, reference, units)
        expected_material = reference(material, "material", fem, "material")
        if (
            not after.get("state_sha256")
            or after.get("material") != expected_material
            or after.get("material_inherited") is not False
            or after.get("orientation") != before["orientation"]
        ):
            raise NXToolError("NX_SIM_READBACK_MISMATCH", "Committed assignment differs")
        return {"collector_state": after, "saved": False, "solve_launched": False}, mark
    except Exception as error:
        outcome = "rolled_back"
        try:
            session.UndoToMark(mark, None)
            session.DeleteUndoMark(mark, None)
        except Exception:
            outcome = "partial"
        raise NXToolError(
            "NX_SIM_MATERIAL_ASSIGNMENT_FAILED",
            "Material assignment failed",
            nx_code=getattr(error, "ErrorCode", None),
            details={
                "mutation_outcome": outcome,
                "cause_code": getattr(error, "code", None),
                "next_step": "Inspect collector assignment before retrying",
            },
        ) from error

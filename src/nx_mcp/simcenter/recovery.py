"""Verified rollback for creation-only thermal boundary operations."""

from nx_mcp.runtime import NXToolError


def authoring_snapshot(sim):
    return {
        "loads": sorted(int(o.Tag) for o in sim.Simulation.Loads),
        "constraints": sorted(int(o.Tag) for o in sim.Simulation.Constraints),
        "expressions": sorted(int(o.Tag) for o in sim.Expressions),
    }


def rollback_creation(session, sim, mark, builder, before, error):
    cleanup = []
    if builder is not None:
        try:
            builder.Destroy()
        except Exception as exc:
            cleanup.append({"stage": "builder_destroy", "nx_code": getattr(exc, "ErrorCode", None)})
    verified = False
    try:
        session.UndoToMark(mark, None)
        verified = authoring_snapshot(sim) == before
        if not verified:
            cleanup.append({"stage": "rollback_readback_mismatch"})
    except Exception as exc:
        cleanup.append({"stage": "undo", "nx_code": getattr(exc, "ErrorCode", None)})
    if verified:
        try:
            session.DeleteUndoMark(mark, None)
        except Exception as exc:
            cleanup.append({"stage": "delete_mark", "nx_code": getattr(exc, "ErrorCode", None)})
    outcome = "rolled_back" if verified and not cleanup else "partial"
    raise NXToolError(
        getattr(error, "code", "NX_SIM_AUTHORING_FAILED")
        if outcome == "rolled_back"
        else "NX_SIM_RECOVERY_INCOMPLETE",
        "Thermal authoring failed; creation was rolled back"
        if outcome == "rolled_back"
        else "Thermal authoring failed and recovery is incomplete; inspect the model before further mutation",
        nx_code=getattr(error, "nx_code", getattr(error, "ErrorCode", None)),
        details={
            "mutation_outcome": outcome,
            "creation_snapshot_restored": verified,
            "cleanup_issues": cleanup,
            "verification_scope": "load, constraint and expression identities; creation-only operation",
        },
    ) from error

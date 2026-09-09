"""Native committed-state failure rollback and preserved geometric associations."""


def run(executor):
    import importlib
    import json
    from pathlib import Path

    from nx_mcp.runtime import NXToolError
    from nx_mcp.simcenter import convection_environment
    from nx_mcp.simcenter.boundaries import create_convection
    from nx_mcp.simcenter.recovery import authoring_snapshot
    from nx_mcp.simcenter.selections import face_inventory

    importlib.reload(convection_environment)
    session = executor.session
    sim = session.Parts.BaseWork
    assert sim.FullPath.endswith("convection_environment_r1.sim")
    flags = {p.FullPath: bool(p.IsModified) for p in session.Parts}
    shared = Path(r"Z:\nx-mcp-integration\simcenter-discovery")
    initial = json.loads((shared / "convection-environment-native.json").read_text())
    faces = face_inventory(session, sim)["rows"]
    current_bounds = {int(row["face"].Tag): row["bounds"] for row in faces}
    association = []
    for i, source in enumerate(("fluid_ambient", "radiative_ambient", "specified")):
        bc = next(b for b in sim.Simulation.Constraints if b.Name == "MCP_ENV_" + source)
        _, members = bc.TargetSetManager.GetTargetSetMembers(0)
        assert len(members) == 1
        bounds = current_bounds[int(members[0].Obj.Tag)]
        assert bounds == initial["faces"]["faces"][i]["bounds"]
        assert bc.Tag in {b.Tag for b in sim.Simulation.ActiveSolution.GetBcs()}
        association.append({"source": source, "bounds": bounds, "solution_member": True})
    before = authoring_snapshot(sim)
    original = convection_environment.verify_convection_properties

    def fail(*args):
        raise NXToolError(
            "NX_SIM_READBACK_MISMATCH",
            "Injected post-commit readback failure for rollback verification",
        )

    convection_environment.verify_convection_properties = fail
    try:
        try:
            create_convection(
                session,
                sim,
                [faces[3]["face"]],
                10.0,
                "MCP_ROLLBACK_PROBE",
                "Injected readback failure fixture",
                "specified",
                293.15,
            )
        except NXToolError as error:
            failure = {"code": error.code, "details": error.details, "message": str(error)}
        else:
            raise AssertionError("Expected injected readback failure")
    finally:
        convection_environment.verify_convection_properties = original
    assert authoring_snapshot(sim) == before
    assert not any(b.Name == "MCP_ROLLBACK_PROBE" for b in sim.Simulation.Constraints)
    assert {p.FullPath: bool(p.IsModified) for p in session.Parts} == flags
    session.ListingWindow.CloseWindow()
    sim.ModelingViews.WorkView.Fit()
    sim.ModelingViews.WorkView.UpdateDisplay()
    return {
        "association_after_reopen_and_save_as": association,
        "injected_failure": failure,
        "native_rollback_verified": True,
        "document_flags_preserved": True,
        "solver_launched": False,
    }

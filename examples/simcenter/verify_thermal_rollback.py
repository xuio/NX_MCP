"""Inject a post-commit inspection failure in the disposable thermal SIM."""


def run(executor):
    import importlib

    from nx_mcp.simcenter import boundaries, recovery
    from nx_mcp.simcenter.selections import face_inventory

    importlib.reload(recovery)
    importlib.reload(boundaries)
    sim = executor.session.Parts.BaseWork
    if not sim.FullPath.endswith(r"F-convection-mcp-20260908-r1\saved_power.sim"):
        raise ValueError("Disposable saved-power SIM required")
    before = recovery.authoring_snapshot(sim)
    original = boundaries.read_properties
    committed = []

    def fail_after_commit(table, nx):
        current = recovery.authoring_snapshot(sim)
        if len(current["constraints"]) != len(before["constraints"]) + 1:
            raise ValueError("Failure injection did not reach the native committed state")
        committed.append(current)
        raise RuntimeError("Intentional post-commit readback failure")

    boundaries.read_properties = fail_after_commit
    try:
        faces = [r["face"] for r in face_inventory(executor.session, sim)["rows"]]
        try:
            boundaries.create_convection(
                executor.session,
                sim,
                faces,
                7.0,
                "MCP_ROLLBACK_READBACK_TEST",
                "Disposable rollback injection; not an engineering boundary",
            )
        except recovery.NXToolError as error:
            if error.details.get("mutation_outcome") != "rolled_back" or not committed:
                raise
            failure = {"code": error.code, "details": error.details}
        else:
            raise ValueError("Injected failure unexpectedly succeeded")
    finally:
        boundaries.read_properties = original
    after = recovery.authoring_snapshot(sim)
    if after != before:
        raise ValueError("Original authoring object identities were not restored")
    return {
        "before": before,
        "committed_before_failure": committed[0],
        "after": after,
        "failure": failure,
        "solver_launched": False,
        "scope": "Native post-commit failure rollback; builder-destroy/undo failures only have local seam tests",
    }

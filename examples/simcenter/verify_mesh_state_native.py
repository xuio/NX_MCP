def run(executor):
    import importlib
    import time

    from nx_mcp.runtime import NXToolError
    from nx_mcp.simcenter import mesh_state

    importlib.reload(mesh_state)
    sim = executor.session.Parts.BaseWork
    assert type(sim).__name__ == "SimPart" and "U-sim-update-export-20260909-r1" in sim.FullPath
    fem = sim.FemPart
    flags = [(p.FullPath, bool(p.IsModified)) for p in executor.session.Parts]
    start = time.monotonic()
    first = mesh_state.capture(fem)
    second = mesh_state.capture(fem)
    assert first == second and first["counts"] == {"elements": 182, "nodes": 73}
    try:
        mesh_state.capture(fem, maximum_entities=10)
    except NXToolError as error:
        assert error.code == "NX_SIM_INSPECTION_LIMIT"
        budget_error = {"code": error.code, "details": error.details}
    else:
        raise AssertionError("Budget limit was ignored")
    return {
        "passed": True,
        "snapshot": first,
        "repeat_comparison": mesh_state.compare(first, second),
        "budget_rejection": budget_error,
        "elapsed_seconds": time.monotonic() - start,
        "flags_unchanged": flags
        == [(p.FullPath, bool(p.IsModified)) for p in executor.session.Parts],
        "solver_launched": False,
    }

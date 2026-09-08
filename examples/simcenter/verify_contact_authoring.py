"""Native contact authoring fixture, both modes tested under outer rollback; no solve."""


def run(executor):
    import runpy
    from nx_mcp.simcenter.solver_guard import require_solver_idle
    from nx_mcp.simcenter.selections import face_inventory

    require_solver_idle()
    create = runpy.run_path(r"Z:\nx-mcp-integration\simcenter-discovery\contact.py")[
        "create_contact"
    ]
    flags = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    fixture = executor._sim_create_benchmark(
        "ui-benchmarks/B-contact-authoring-20260909-r1",
        length_mm=10.0,
        width_mm=10.0,
        height_mm=10.0,
        block_origins_mm=[[0.0, 0.0, 0.0], [10.0, 0.0, 0.0]],
    )
    sim = executor.session.Parts.BaseWork
    rows = face_inventory(executor.session, sim)["rows"]
    interface = [
        r["face"]
        for r in rows
        if abs(r["bounds"]["minimum"][0] - 10) < 1e-6 and abs(r["bounds"]["maximum"][0] - 10) < 1e-6
    ]
    assert len(interface) == 2
    results = []
    for mode, value in [("resistance", 0.5), ("conductance", 2.0)]:
        mark = executor.session.SetUndoMark(
            executor.nxopen.Session.MarkVisibility.Invisible, "Test contact mode"
        )
        try:
            result = create(
                executor.session,
                sim,
                [interface[0]],
                [interface[1]],
                mode,
                value,
                "MCP_CONTACT_" + mode,
                "Assumed generic API fixture",
            )
            result.pop("boundary")
            results.append(result)
        finally:
            executor.session.UndoToMark(mark, None)
            executor.session.DeleteUndoMark(mark, None)
    assert not list(sim.Simulation.SimulationObjects)
    after = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    assert all(after[p] == v for p, v in flags.items())
    return {
        "fixture": fixture,
        "modes": results,
        "outer_rollback_verified": True,
        "unrelated_modified_flags_preserved": True,
        "solver_launched": False,
    }

"""Native steady-control authoring/readback/persistence on an isolated SIM copy."""


def run(executor):
    import json
    import runpy
    import shutil
    from pathlib import Path

    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    module = runpy.run_path(r"Z:\nx-mcp-integration\simcenter-discovery\steady_controls.py")
    configure = module["configure"]
    read = module["read_controls"]
    flags = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    root = executor.workspace.resolve("ui-benchmarks/B-contact-explicit-20260909-r1")
    root.mkdir()
    source = executor.workspace.resolve(
        "ui-benchmarks/B-contact-resistance-export-20260909-r1/contact_resistance_r1.sim"
    )
    path = root / "contact_explicit_r1.sim"
    shutil.copy2(source, path)
    executor._sim_open(str(path))
    sim = executor.session.Parts.BaseWork
    trials = []
    for fraction in (None, 0.001):
        mark = executor.session.SetUndoMark(
            executor.nxopen.Session.MarkVisibility.Invisible, "Trial steady control mode"
        )
        try:
            result = configure(executor.session, sim, 0.001, 100, fraction)
            result.pop("table")
            trials.append(result)
        finally:
            executor.session.UndoToMark(mark, None)
            executor.session.DeleteUndoMark(mark, None)
    final = configure(executor.session, sim, 0.001, 100, 0.001)
    final.pop("table")
    sid = executor._reference(sim, "part", sim, "SIM")["id"]
    executor._sim_save(sid)
    executor._sim_close(sid)
    opened = executor._sim_open(str(path))
    sim = executor.session.Parts.BaseWork
    table = sim.Simulation.ActiveSolution.PropertyTable.GetNamedPropertyTablePropertyValue(
        "Thermal Parameters"
    )
    after = read(table.PropertyTable)
    assert after == final["actual"]
    sid = executor._reference(sim, "part", sim, "SIM")["id"]
    executor._sim_save(sid)
    current = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    assert all(current[p] == v for p, v in flags.items())
    result = {
        "trials": trials,
        "final": final,
        "reopened": after,
        "open_warnings": opened.get("warnings", []),
        "document": sid,
        "path": str(path),
        "unrelated_modified_flags_preserved": True,
        "solver_launched": False,
    }
    Path(r"Z:\nx-mcp-integration\simcenter-discovery\steady-controls-native.json").write_text(
        json.dumps(result, indent=2)
    )
    return result

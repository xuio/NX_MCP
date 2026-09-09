def run(executor):
    import importlib
    import json
    import shutil
    import types

    from nx_mcp import hardened
    from nx_mcp.simcenter import heat_loads, heat_schedule, native

    importlib.reload(heat_schedule)
    importlib.reload(heat_loads)
    importlib.reload(native)
    method = types.MethodType(native.SimcenterMixin._sim_heat_schedule, executor)
    executor._sim_heat_schedule = method
    executor._handlers["nx_sim_heat_schedule"] = method
    hardened.NON_MODEL.add("nx_sim_heat_schedule")
    from pathlib import Path

    from nx_mcp.simcenter import scalar_tables
    from nx_mcp.simcenter.solver_guard import require_solver_idle
    from nx_mcp.simcenter.time_controls import configure_transient_steps

    require_solver_idle()
    session = executor.session
    flags = {p.FullPath: bool(p.IsModified) for p in session.Parts}
    fixture = executor._sim_create_benchmark(
        "ui-benchmarks/T-heat-schedule-20260909-r1", length_mm=10, width_mm=10, height_mm=10
    )
    sim = session.Parts.BaseWork
    sid = executor._reference(sim, "part", sim, "SIM")["id"]
    fem = sim.FemPart
    fid = executor._reference(fem, "part", fem, "FEM")["id"]
    mesh = executor._sim_mesh(fid, 5.0)
    executor._sim_material(
        fid, "MCP_TIME_SOLID", 200.0, 2700.0, 900.0, "Generic time-load API fixture", True
    )
    executor._sim_save(fid)
    executor._sim_activate(sid)
    m = {
        "name": "MCP_TIME_POWER",
        "axis": "time",
        "quantity": "power",
        "samples": [[0, 0], [10, 1], [20, 0]],
        "provenance": "Generic time heat API fixture",
    }
    result = scalar_tables.create(session, sim, m)
    table = result.pop("table")
    times = configure_transient_steps(
        session, sim, [0, 10, 20], max_temperature_change_k=1, min_time_step_s=0.01
    )
    bodyid = executor._reference(list(fem.Bodies)[0], "body", fem, "body")["id"]
    fieldid = executor._reference(table, "simulation_field", sim, "field")["id"]
    committed = executor._sim_heat_schedule(
        sid, bodyid, fieldid, "MCP_TIME_HEAT", "Generic native schedule fixture", scale=2.0
    )
    props = committed["properties"]
    assert committed["schedule"]["samples_w"] == [[0, 0], [10, 2], [20, 0]]
    executor._sim_save(sid)
    copied = executor._sim_save_as(
        sid, "ui-benchmarks/T-heat-schedule-export-20260909-r2/heat_schedule_r1.sim"
    )
    sid = copied["document"]["id"]
    exported = executor._sim_export_input(sid)
    root = Path(r"Z:\nx-mcp-integration\simcenter-discovery")
    shutil.copy2(exported["input_path"], root / "heat-schedule-native.xml")
    session.ListingWindow.CloseWindow()
    sim.ModelingViews.WorkView.Fit()
    sim.ModelingViews.WorkView.UpdateDisplay()
    assert all(
        {p.FullPath: bool(p.IsModified) for p in session.Parts}[k] == v for k, v in flags.items()
    )
    receipt = {
        "fixture": fixture,
        "document": sid,
        "path": sim.FullPath,
        "mesh": mesh,
        "table": result,
        "committed": committed,
        "load_properties": props,
        "time_controls": times,
        "export": exported,
        "target_verified": True,
        "solution_membership_verified": True,
        "unrelated_flags_preserved": True,
        "solver_launched": False,
    }
    (root / "heat-schedule-native.json").write_text(json.dumps(receipt, indent=2))
    return receipt

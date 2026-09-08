"""One tiny coupled diagnostic. Not an acceptance run; never blind-relaunch."""


def run(executor):
    import importlib
    import json
    import time

    import NXOpen as nx

    from nx_mcp.simcenter.solver_guard import require_solver_idle

    for module in ("input_export", "preparation", "native_launch"):
        importlib.reload(importlib.import_module("nx_mcp.simcenter." + module))
    require_solver_idle()
    sim = executor.session.Parts.BaseWork
    if "E-ambient-time-table-20260908-r1" not in sim.FullPath:
        raise ValueError("Unexpected current diagnostic source")
    receipt = executor.workspace.resolve("ui-benchmarks/E-diagnostic-r1-launch.json")
    if receipt.exists():
        return {
            "replayed": True,
            "receipt": json.loads(receipt.read_text()),
            "solver_relaunched": False,
        }
    rows = {}

    def record(key, value):
        rows[key] = value
        receipt.write_text(json.dumps(rows, indent=2))

    record(
        "scope",
        {
            "acceptance": False,
            "known_ambient_export_mismatch": True,
            "interface_connection_unverified": True,
            "iteration_caps": 100,
        },
    )
    sid = executor._reference(sim, "part", sim, "SIM")["id"]
    record(
        "copy",
        executor._sim_save_as(
            sid, "ui-benchmarks/E-diagnostic-20260908-r1/coupled_diagnostic_r1.sim"
        ),
    )
    solution = sim.Simulation.ActiveSolution
    mark = executor.session.SetUndoMark(
        nx.Session.MarkVisibility.Visible, "MCP bounded coupled diagnostic"
    )
    try:
        controls = []
        for key, property_name in [
            ("Thermal Parameters", "Thermal Steady State - Iteration Limit"),
            ("Flow Solution Parameters", "3D Flow Steady State - Iteration Limit"),
        ]:
            table = solution.PropertyTable.GetNamedPropertyTablePropertyValue(key).PropertyTable
            table.SetIntegerPropertyValue(property_name, 100)
            actual = table.GetIntegerPropertyValue(property_name)
            assert actual == 100
            controls.append({"name": property_name, "value": actual})
        solution.PropertyTable.SetIntegerPropertyValue("Turbulence Model", 0)
        assert solution.PropertyTable.GetIntegerPropertyValue("Turbulence Model") == 0
        surface = solution.PropertyTable.GetNamedPropertyTablePropertyValue(
            "Flow Surface Parameters"
        ).PropertyTable
        surface.SetIntegerPropertyValue("Wall Treatment", 0)
        assert surface.GetIntegerPropertyValue("Wall Treatment") == 0
    except Exception:
        executor.session.UndoToMark(mark, None)
        raise
    record("controls", controls)
    status = sim.Save(nx.BasePart.SaveComponents.FalseValue, nx.BasePart.CloseAfterSave.FalseValue)
    if status:
        status.Dispose()
    sid = executor._reference(sim, "part", sim, "SIM")["id"]
    started = time.monotonic()
    record("prepare", executor._sim_prepare_solve(sid, "coupled-diagnostic-r1"))
    record("prepare_seconds", time.monotonic() - started)
    record(
        "launch_intent",
        "Inspect persistent job coupled-diagnostic-r1 after any interruption; never relaunch",
    )
    record("launch", executor._sim_launch(sid, "coupled-diagnostic-r1"))
    return rows

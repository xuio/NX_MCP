"""Reload an isolated saved coupled SIM, then verify native ambient export."""


def run(executor):
    import json
    import time

    from nx_mcp.runtime import NXToolError
    from nx_mcp.simcenter.input_export import export_flow_input
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    sim = executor.session.Parts.BaseWork
    if "E-environment-copy-property-20260908-r1" not in sim.FullPath:
        raise ValueError("Unexpected SIM")
    root = executor.workspace.resolve("ui-benchmarks/E-ambient-reopen-20260908-r1")
    if root.exists():
        raise ValueError("Inspect prior lifecycle receipt; do not repeat")
    receipt = executor.workspace.resolve("ui-benchmarks/E-ambient-reopen-r1.json")
    rows = {}

    def record(key, value):
        rows[key] = value
        receipt.write_text(json.dumps(rows, indent=2))

    copied = executor._sim_save_as(
        executor._reference(sim, "part", sim, "SIM")["id"], str(root / "coupled_reopen_r1.sim")
    )
    record("copy", copied)
    path = sim.FullPath
    started = time.monotonic()
    record("close", executor._sim_close(executor._reference(sim, "part", sim, "SIM")["id"]))
    record("open", executor._sim_open(path))
    sim = executor.session.Parts.BaseWork
    assert sim.FullPath == path
    value, unit = sim.Simulation.ActiveSolution.PropertyTable.GetScalarWithDataPropertyValue(
        "Fluid Temperature"
    )
    record("reopened_ambient", {"value": value, "units": unit.Name})
    try:
        result = export_flow_input(executor.session, executor.workspace, sim)
        record("export", result)
    except NXToolError as error:
        record("export", {"error_code": error.code, "details": error.details})
    record("elapsed_seconds", time.monotonic() - started)
    record("solver_launched", False)
    return rows

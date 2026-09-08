"""Inspect and scale an existing constant field on an isolated saved SIM copy."""


def run(executor):
    import importlib
    import json

    import NXOpen as nx

    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    properties = importlib.reload(importlib.import_module("nx_mcp.simcenter.properties"))
    importlib.reload(importlib.import_module("nx_mcp.simcenter.boundary_state"))
    source = executor.workspace.resolve(
        "ui-benchmarks/E-environment-field-20260908-r1/coupled_field_r1.sim"
    )
    root = executor.workspace.resolve("ui-benchmarks/F1-field-scale-audit-20260908-r1")
    if root.exists():
        raise ValueError("Inspect retained field audit before retry")
    executor._sim_open(str(source))
    sim = executor.session.Parts.BaseWork
    executor._sim_save_as(
        executor._reference(sim, "part", sim, "SIM")["id"], str(root / "field_scale.sim")
    )
    table = sim.Simulation.ActiveSolution.PropertyTable
    wrapper = table.GetScalarFieldWrapperPropertyValue("Absolute Pressure")
    if wrapper.GetField() is None:
        raise ValueError("Expected retained field-backed pressure")

    def read():
        return next(
            r for r in properties.read_properties(table, nx) if r["name"] == "Absolute Pressure"
        )

    before = read()
    scale = wrapper.GetFieldScaleFactor()
    mark = executor.session.SetUndoMark(
        nx.Session.MarkVisibility.Visible, "MCP field scale readback"
    )
    try:
        wrapper.SetField(wrapper.GetField(), scale * 2)
        after = read()
        if after.get("field_scale") != scale * 2:
            raise ValueError("Scale readback differs")
        if (
            "evaluated_value" in before
            and after["evaluated_value"] != before["evaluated_value"] * 2
        ):
            raise ValueError("Constant field readback differs")
    finally:
        executor.session.UndoToMark(mark, None)
    restored = read()
    if restored != before:
        raise ValueError("Field audit rollback differs")
    result = {
        "before": before,
        "after": after,
        "restored": restored,
        "native_scale_readback_verified": True,
        "save_reopen_export": "pending; this probe does not claim it",
        "solver_launched": False,
    }
    (root / "verification.json").write_text(json.dumps(result, indent=2))
    return result

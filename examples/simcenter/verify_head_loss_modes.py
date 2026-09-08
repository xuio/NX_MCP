"""Native selector regression on an isolated copy; no solver launch."""


def run(executor):
    import importlib

    import NXOpen as nx

    from nx_mcp.runtime import NXToolError
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    module = importlib.reload(importlib.import_module("nx_mcp.simcenter.head_loss"))
    root = executor.workspace.resolve("ui-benchmarks/D-head-loss-mode-audit-20260908-r1")
    if root.exists():
        raise ValueError("Inspect existing audit copy before retry")
    source = executor.workspace.resolve(
        "ui-benchmarks/D-head-loss-mcp-20260908-r1/head_loss_test_r1.sim"
    )
    executor._sim_open(str(source))
    sim = executor.session.Parts.BaseWork
    executor._sim_save_as(
        executor._reference(sim, "part", sim, "SIM")["id"], str(root / "mode_audit.sim")
    )
    candidates = [
        b
        for b in sim.Simulation.SimulationObjects
        if b.DescriptorName == "Opening"
        and b.PropertyTable.GetNamedPropertyTablePropertyValue("Head Loss") is not None
    ]
    if len(candidates) != 1:
        raise ValueError("Expected one retained opening loss")
    boundary = candidates[0]
    table = boundary.PropertyTable.GetNamedPropertyTablePropertyValue("Head Loss")
    props = table.PropertyTable
    old, unit = props.GetBaseScalarWithDataPropertyValue("Head Loss Coefficient")
    selectors = {key: props.GetIntegerPropertyValue(key) for key in ("Type", "Proportional to")}
    mark = executor.session.SetUndoMark(
        nx.Session.MarkVisibility.Visible, "MCP head-loss selector audit"
    )
    rows = []
    try:
        for mode, proportional in [(1, 0), (0, 1)]:
            props.SetIntegerPropertyValue("Type", mode)
            props.SetIntegerPropertyValue("Proportional to", proportional)
            for requested in [old, old + 0.25]:
                try:
                    module.set_opening_head_loss(
                        executor.session, sim, boundary, requested, expected_coefficient=old
                    )
                except NXToolError as error:
                    if error.code != "NX_SIM_HEAD_LOSS_MODE":
                        raise
                    if props.GetBaseScalarWithDataPropertyValue("Head Loss Coefficient") != (
                        old,
                        unit,
                    ):
                        raise ValueError("Rejected edit changed coefficient") from error
                    rows.append(
                        {
                            "selectors": [mode, proportional],
                            "requested": requested,
                            "code": error.code,
                            "coefficient_unchanged": True,
                        }
                    )
                else:
                    raise ValueError("Inactive coefficient was accepted")
        props.SetIntegerPropertyValue("Type", 0)
        props.SetIntegerPropertyValue("Proportional to", 0)
        rows.append(
            module.set_opening_head_loss(
                executor.session, sim, boundary, old + 0.25, expected_coefficient=old
            )
        )
    finally:
        executor.session.UndoToMark(mark, None)
    if props.GetBaseScalarWithDataPropertyValue("Head Loss Coefficient") != (old, unit) or any(
        props.GetIntegerPropertyValue(k) != v for k, v in selectors.items()
    ):
        raise ValueError("Audit rollback differs")
    return {
        "rows": rows,
        "audit_changes_rolled_back": True,
        "solver_launched": False,
        "scope": "Native internal adapter; public MCP replay/export checks remain separate",
    }

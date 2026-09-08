"""Detach the loss table only on the disposable public head-loss test copy."""


def run(executor):
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    sim = executor.session.Parts.BaseWork
    assert sim.FullPath.endswith(r"D-head-loss-mcp-20260908-r1\head_loss_test_r1.sim")
    opening = next(b for b in sim.Simulation.SimulationObjects if b.Name == "Duct Opening")
    props = opening.PropertyTable
    table = props.GetNamedPropertyTablePropertyValue("Head Loss")
    assert table is not None and table.Name != "Public opening loss"
    assert table.PropertyTable.GetBaseScalarWithDataPropertyValue("Head Loss Coefficient")[0] == 0
    props.SetNamedPropertyTablePropertyValue("Head Loss", None)
    assert props.GetNamedPropertyTablePropertyValue("Head Loss") is None
    return {
        "fixture": sim.FullPath,
        "detached_table_name": table.Name,
        "table_deleted": False,
        "saved": False,
        "solver_launched": False,
    }

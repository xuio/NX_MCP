"""Verify convergence assignment and explicit rollback on the isolated duct SIM."""


def run(executor):
    import importlib

    import NXOpen as nx

    from nx_mcp.simcenter import flow_controls
    from nx_mcp.simcenter.properties import read_properties

    importlib.reload(flow_controls)
    session = executor.session
    sim = session.Parts.BaseWork
    if type(sim).__name__ != "SimPart" or "D-cavity-documents-20260908-r2" not in sim.FullPath:
        raise ValueError("Isolated duct SIM required")
    table = sim.Simulation.ActiveSolution.PropertyTable.GetNamedPropertyTablePropertyValue(
        "Flow Solution Parameters"
    ).PropertyTable
    before = read_properties(table, nx)
    mark = session.SetUndoMark(
        nx.Session.MarkVisibility.Visible, "Verify flow convergence controls"
    )
    try:
        result = flow_controls.configure_convergence(
            session, sim, residual=1e-6, flow_imbalance_fraction=0.001, iteration_limit=1000
        )
        repeat = flow_controls.configure_convergence(
            session, sim, residual=1e-6, flow_imbalance_fraction=0.001, iteration_limit=1000
        )
        if repeat["changed"]:
            raise ValueError("Repeated assignment was not idempotent")
    finally:
        session.UndoToMark(mark, None)
        session.DeleteUndoMark(mark, None)
    after = read_properties(table, nx)
    if before != after:
        raise ValueError("Explicit rollback did not restore all flow parameters")
    return {
        "assignment": result,
        "repeat": repeat,
        "rollback_verified": True,
        "saved": False,
        "solver_launched": False,
    }

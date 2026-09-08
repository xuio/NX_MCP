"""Bounded probe of the Inlet Conditions reference already exposed by NX."""


def run(executor):
    import time
    import NXOpen as nx
    from nx_mcp.simcenter.properties import read_properties
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    sim = executor.session.Parts.BaseWork
    if "E-environment-field-20260908-r1" not in sim.FullPath:
        raise ValueError("Unexpected SIM")
    before = {int(t.Tag) for t in sim.ModelingObjectPropertyTables}
    mark = executor.session.SetUndoMark(
        nx.Session.MarkVisibility.Visible, "MCP inlet condition descriptor probe"
    )
    started = time.monotonic()
    result = {
        "hypothesis": "The native Inlet Conditions boundary reference uses a modeling object table of the same descriptor name",
        "solver_launched": False,
    }
    try:
        table = sim.ModelingObjectPropertyTables.CreateModelingObjectPropertyTable(
            "Inlet Conditions",
            "NX MULTIPHYSICS - Coupled Thermal-Flow",
            "NX MULTIPHYSICS",
            "Probe inlet conditions",
            0,
        )
        result.update(
            accepted=True,
            descriptor=table.DescriptorType,
            properties=read_properties(table.PropertyTable, nx),
        )
    except Exception as error:
        result.update(accepted=False, nx_code=getattr(error, "ErrorCode", None), message=str(error))
    finally:
        executor.session.UndoToMark(mark, None)
        assert before == {int(t.Tag) for t in sim.ModelingObjectPropertyTables}
        executor.session.DeleteUndoMark(mark, None)
    result.update(rollback_verified=True, elapsed_seconds=time.monotonic() - started)
    return result

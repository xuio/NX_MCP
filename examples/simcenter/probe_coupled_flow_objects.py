"""Inspect installed command descriptors without committing objects."""


def run(executor):
    import time
    import NXOpen as nx
    from nx_mcp.simcenter.properties import read_properties
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    sim = executor.session.Parts.BaseWork
    if "E-environment-field-20260908-r1" not in sim.FullPath:
        raise ValueError("Unexpected SIM")
    rows = []
    for descriptor in ("Flow Boundary Condition", "Flow Surface"):
        started = time.monotonic()
        before = {int(b.Tag) for b in sim.Simulation.SimulationObjects}
        mark = executor.session.SetUndoMark(
            nx.Session.MarkVisibility.Visible, "MCP coupled object schema"
        )
        builder = None
        row = {"descriptor": descriptor}
        try:
            builder = sim.Simulation.CreateBcBuilderForSimulationObjectDescriptor(
                descriptor, "Probe " + descriptor
            )
            row.update(
                accepted=True,
                properties=read_properties(builder.PropertyTable, nx),
                target_sets=builder.TargetSetManager.TargetSetCount,
            )
        except Exception as error:
            row.update(
                accepted=False, nx_code=getattr(error, "ErrorCode", None), message=str(error)
            )
        finally:
            if builder:
                builder.Destroy()
            executor.session.UndoToMark(mark, None)
            assert before == {int(b.Tag) for b in sim.Simulation.SimulationObjects}
            executor.session.DeleteUndoMark(mark, None)
        row.update(rollback_verified=True, elapsed_seconds=time.monotonic() - started)
        rows.append(row)
    inlet = next(b for b in sim.Simulation.SimulationObjects if b.Name == "Coupled Inlet")
    key = "Inlet Conditions"
    return {
        "rows": rows,
        "inlet_condition_property_type": str(inlet.PropertyTable.GetPropertyType(key)),
        "solver_launched": False,
    }

"""Bounded check of the installed Open CAE Contact Thermal Coupling descriptor."""


def run(executor):
    from nx_mcp.simcenter.solver_guard import require_solver_idle
    from nx_mcp.simcenter.properties import read_properties

    require_solver_idle()
    session = executor.session
    flags = {p.FullPath: bool(p.IsModified) for p in session.Parts}
    executor._sim_open(
        str(
            executor.workspace.resolve(
                "ui-benchmarks/B-contact-context-20260908-r2/contact_context_r2.sim"
            )
        )
    )
    sim = session.Parts.BaseWork
    assert sim.Simulation.ActiveSolution.AnalysisType == "Thermal"
    objects = [int(o.Tag) for o in sim.Simulation.SimulationObjects]
    mark = session.SetUndoMark(
        executor.nxopen.Session.MarkVisibility.Invisible, "Inspect documented contact descriptor"
    )
    builder = None
    try:
        builder = sim.Simulation.CreateBcBuilderForSimulationObjectDescriptor(
            "Contact Thermal Coupling", "MCP_CONTACT_DESCRIPTOR_CHECK"
        )
        result = {
            "descriptor": builder.PropertyTable.DescriptorNeutralName,
            "properties": read_properties(builder.PropertyTable, executor.nxopen),
            "target_set_count": builder.TargetSetManager.TargetSetCount,
            "committed": False,
            "source": "Open CAE NX MULTIPHYSICS - Thermal / Contact Thermal Coupling",
            "solver_launched": False,
        }
    finally:
        if builder is not None:
            builder.Destroy()
        session.UndoToMark(mark, None)
        session.DeleteUndoMark(mark, None)
    assert objects == [int(o.Tag) for o in sim.Simulation.SimulationObjects]
    after = {p.FullPath: bool(p.IsModified) for p in session.Parts}
    assert all(after[p] == v for p, v in flags.items())
    result["unrelated_modified_flags_preserved"] = True
    return result

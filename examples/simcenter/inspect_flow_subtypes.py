def run(executor):
    import NXOpen.CAE as cae

    from nx_mcp.simcenter.properties import read_properties

    session = executor.session
    matches = [
        p
        for p in session.Parts
        if isinstance(p, cae.SimPart) and "D-flow-mcp-20260908" in p.FullPath
    ]
    if len(matches) != 1:
        raise ValueError("Requires isolated Flow SIM")
    sim = matches[0]
    oldwork, olddisplay = session.Parts.BaseWork, session.Parts.BaseDisplay
    before = {int(x.Tag) for x in sim.Simulation.SimulationObjects}
    result = {
        "source": "Installed cae_lang_commands.xml Flow Boundary Condition synonyms; native names are candidates, not assumed support",
        "probes": [],
    }
    try:
        _, status = session.Parts.SetDisplay(sim, False, False)
        if status:
            status.Dispose()
        session.Parts.SetWork(sim)
        for name in [
            "Inlet",
            "Outlet",
            "Opening",
            "Internal Fan",
            "Initial Fluid Pressure",
            "Initial Fluid Velocity",
        ]:
            mark = session.SetUndoMark(
                executor.nxopen.Session.MarkVisibility.Visible, "Inspect native Flow descriptor"
            )
            builder = None
            try:
                creator = (
                    sim.Simulation.CreateBcBuilderForConstraintDescriptor
                    if name.startswith("Initial")
                    else sim.Simulation.CreateBcBuilderForSimulationObjectDescriptor
                )
                builder = creator(name, "MCP descriptor inspection")
                result["probes"].append(
                    {
                        "name": name,
                        "builder_created": True,
                        "properties": read_properties(builder.PropertyTable, executor.nxopen),
                    }
                )
            except Exception as ex:
                result["probes"].append(
                    {
                        "name": name,
                        "builder_created": False,
                        "error": str(ex),
                        "nx_code": getattr(ex, "ErrorCode", None),
                    }
                )
            finally:
                if builder is not None:
                    builder.Destroy()
                session.UndoToMark(mark, None)
                session.DeleteUndoMark(mark, None)
        result["simulation_objects_unchanged"] = before == {
            int(x.Tag) for x in sim.Simulation.SimulationObjects
        }
        result["constraints_after"] = len(list(sim.Simulation.Constraints))
        result["committed_boundaries"] = 0
        return result
    finally:
        _, status = session.Parts.SetDisplay(olddisplay, False, False)
        if status:
            status.Dispose()
        session.Parts.SetWork(oldwork)

def run(executor):
    s = executor.session
    sim = s.Parts.BaseWork
    if "C-transient-fine-20260908" not in sim.FullPath:
        raise ValueError("Requires isolated benchmark")
    from nx_mcp.simcenter.properties import read_properties

    records = []
    before = [int(x.Tag) for x in sim.Simulation.SimulationObjects]
    for descriptor in ["Interface Resistance", "Face Contact", "Thermal Coupling"]:
        mark = s.SetUndoMark(
            executor.nxopen.Session.MarkVisibility.Visible,
            "Inspect legacy contact API and rollback",
        )
        try:
            obj = sim.Simulation.SimulationObjects.CreateSimulationObject(
                descriptor, "MCP_INSPECT_CONTACT"
            )
            records.append(
                {
                    "requested_descriptor": descriptor,
                    "accepted": True,
                    "neutral": obj.PropertyTable.DescriptorNeutralName,
                    "properties": read_properties(obj.PropertyTable, executor.nxopen),
                }
            )
        except Exception as ex:
            records.append(
                {
                    "requested_descriptor": descriptor,
                    "accepted": False,
                    "error": str(ex),
                    "nx_code": getattr(ex, "ErrorCode", None),
                }
            )
        finally:
            s.UndoToMark(mark, None)
            s.DeleteUndoMark(mark, None)
            if [int(x.Tag) for x in sim.Simulation.SimulationObjects] != before:
                raise ValueError("Rollback did not restore simulation object set")
    return {
        "api": "SimulationObjects.CreateSimulationObject (deprecated NX2306)",
        "descriptors": records,
        "rollback_verified": True,
    }

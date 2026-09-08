def run(executor):
    import importlib
    from nx_mcp.simcenter import contact
    from nx_mcp.simcenter.selections import face_inventory

    importlib.reload(contact)
    sim = executor.session.Parts.BaseWork
    assert "B-contact-authoring-20260909-r1" in sim.FullPath
    flags = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    bc = next(b for b in sim.Simulation.SimulationObjects if b.Name == "MCP_PUBLIC_CONTACT_R1")
    rows = face_inventory(executor.session, sim)["rows"]
    interface = [
        r["face"]
        for r in rows
        if abs(r["bounds"]["minimum"][0] - 10) < 1e-6 and abs(r["bounds"]["maximum"][0] - 10) < 1e-6
    ]
    assert len(interface) == 2
    targets = []
    for index in range(2):
        _, members = bc.TargetSetManager.GetTargetSetMembers(index)
        actual = [m.Obj for m in members if m is not None and m.Obj is not None]
        assert actual == [interface[index]]
        targets.append(
            {
                "index": index,
                "count": len(actual),
                "prototype_journal": actual[0].Prototype.JournalIdentifier,
            }
        )
    props = contact.read_properties(bc.PropertyTable, executor.nxopen)
    row = next(p for p in props if p["name"] == "Total Resistance")
    contact.verify_contact_value(row, 0.5, "ThermalResistance_Metric4")
    assert flags == {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    return {
        "passed": True,
        "reopened_primary_secondary_geometry_verified": True,
        "targets": targets,
        "resistance_readback": row,
        "unrelated_modified_flags_preserved": True,
        "solver_launched": False,
    }

"""Create an analysis-only equivalent G=2 W/K variant, reopen and export it."""


def run(executor):
    import json, shutil
    from pathlib import Path
    from nx_mcp.simcenter.contact import verify_contact_value
    from nx_mcp.simcenter.properties import read_properties
    from nx_mcp.simcenter.input_export import export_flow_input
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    session = executor.session
    source = session.Parts.BaseWork
    assert source.FullPath.endswith("contact_resistance_r1.sim")
    flags = {p.FullPath: bool(p.IsModified) for p in session.Parts}
    root = executor.workspace.resolve("ui-benchmarks/B-contact-conductance-export-20260909-r1")
    root.mkdir()
    path = root / "contact_conductance_r1.sim"
    shutil.copy2(source.FullPath, path)
    executor._sim_open(str(path))
    sim = session.Parts.BaseWork
    bc = next(
        b
        for b in sim.Simulation.SimulationObjects
        if b.DescriptorName == "Contact Thermal Coupling"
    )
    mark = session.SetUndoMark(
        executor.nxopen.Session.MarkVisibility.Visible, "Equivalent conductance analysis variant"
    )
    try:
        props = bc.PropertyTable
        props.SetIntegerPropertyValue("Type", 0)
        props.SetBooleanPropertyValue("Per Element", False)
        unit = sim.UnitCollection.FindObject("ThermalConductance_Metric4")
        assert unit.Symbol == "W/dK"
        exp = sim.Expressions.CreateSystemNumberExpression("2.0", unit)
        props.SetScalarFieldWrapperPropertyValue(
            "Total Conductance", sim.FieldManager.CreateScalarFieldWrapperWithExpression(exp)
        )
        before = next(
            r for r in read_properties(props, executor.nxopen) if r["name"] == "Total Conductance"
        )
        verify_contact_value(before, 2.0, unit.Name)
        assert props.GetIntegerPropertyValue("Type") == 0 and not props.GetBooleanPropertyValue(
            "Per Element"
        )
    except Exception:
        session.UndoToMark(mark, None)
        session.DeleteUndoMark(mark, None)
        raise
    sid = executor._reference(sim, "part", sim, "SIM")["id"]
    executor._sim_save(sid)
    executor._sim_close(sid)
    opened = executor._sim_open(str(path))
    sim = session.Parts.BaseWork
    bc = next(
        b
        for b in sim.Simulation.SimulationObjects
        if b.DescriptorName == "Contact Thermal Coupling"
    )
    props = bc.PropertyTable
    after = next(
        r for r in read_properties(props, executor.nxopen) if r["name"] == "Total Conductance"
    )
    assert (
        before == after
        and props.GetIntegerPropertyValue("Type") == 0
        and not props.GetBooleanPropertyValue("Per Element")
    )
    targets = []
    for i in range(2):
        _, members = bc.TargetSetManager.GetTargetSetMembers(i)
        faces = [m.Obj for m in members if m is not None and m.Obj is not None]
        assert len(faces) == 1
        targets.append(faces[0].Prototype.JournalIdentifier)
    assert len(set(targets)) == 2
    executor._sim_save(executor._reference(sim, "part", sim, "SIM")["id"])
    exported = export_flow_input(session, executor.workspace, sim)
    shutil.copy2(
        exported["input_path"],
        Path(r"Z:\nx-mcp-integration\simcenter-discovery\contact-conductance.xml"),
    )
    current = {p.FullPath: bool(p.IsModified) for p in session.Parts}
    assert all(current[p] == v for p, v in flags.items())
    return {
        "passed": True,
        "before": before,
        "after": after,
        "target_prototypes": targets,
        "export": exported,
        "open_warnings": opened.get("warnings", []),
        "unrelated_modified_flags_preserved": True,
        "solver_launched": False,
        "scope": "Native equivalent conductance variant, save/reopen and export; not public contact editing",
    }

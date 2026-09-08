"""Reversible native static fan assignment on the isolated duct benchmark."""


def run(executor):
    import importlib

    from nx_mcp.runtime import NXToolError
    from nx_mcp.simcenter import fan_boundary, fan_field

    importlib.reload(fan_boundary)
    importlib.reload(fan_field)
    import nx_mcp.simcenter.solver_guard as solver_guard
    import nx_mcp.simcenter.time_controls as time_controls

    importlib.reload(solver_guard)
    importlib.reload(time_controls)
    session, nx = executor.session, executor.nxopen
    original_work, original_display = session.Parts.BaseWork, session.Parts.BaseDisplay
    original_flags = {p.FullPath: bool(p.IsModified) for p in session.Parts}
    sim = next(
        p
        for p in session.Parts
        if p.FullPath.endswith(r"F-input-export-20260908-r2\flow_input_r2.sim")
    )
    _, status = session.Parts.SetDisplay(sim, False, False)
    if status:
        status.Dispose()
    session.Parts.SetWork(sim)
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "Verify static fan assignment")
    inlet = next(b for b in sim.Simulation.SimulationObjects if b.Name == "Duct Inlet")
    before = fan_boundary.binding(inlet.PropertyTable)
    fields = {f.Tag for f in sim.FieldManager.Fields}
    try:
        created = fan_field.create_fan_table(
            session,
            sim,
            {
                "name": "MCP reversible static fan assignment",
                "pressure_convention": "static",
                "rpm": 1000,
                "reference_density_kg_m3": 1.2,
                "points": [
                    {"flow_m3_s": 0, "pressure_Pa": 1},
                    {"flow_m3_s": 0.0004, "pressure_Pa": 0},
                ],
                "stall_region": "Synthetic only",
                "provenance": {"kind": "assumed", "source": "Native assignment fixture"},
            },
        )
        table = created["table"]
        result = fan_boundary.assign_static_fan(session, sim, inlet, table)
        assert result["binding"]["field_tag"] == int(table.Tag)
        successful = fan_boundary.binding(inlet.PropertyTable)
        alternative = fan_field.create_fan_table(
            session,
            sim,
            {
                **result["manifest"],
                "name": "MCP rollback alternative fan",
                "points": [
                    {"flow_m3_s": 0, "pressure_Pa": 2},
                    {"flow_m3_s": 0.0004, "pressure_Pa": 0},
                ],
            },
        )["table"]
        real_binding = fan_boundary.binding
        calls = 0

        def injected(properties):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise NXToolError("NX_SIM_READBACK_MISMATCH", "Injected readback failure")
            return real_binding(properties)

        fan_boundary.binding = injected
        try:
            try:
                fan_boundary.assign_static_fan(session, sim, inlet, alternative)
            except NXToolError as error:
                assert error.details["mutation_outcome"] == "rolled_back"
            else:
                raise AssertionError("Injected failure ignored")
        finally:
            fan_boundary.binding = real_binding
        assert fan_boundary.binding(inlet.PropertyTable) == successful
        result["injected_failure_rollback_verified"] = True
    finally:
        session.UndoToMark(mark, None)
        session.DeleteUndoMark(mark, None)
        assert fan_boundary.binding(inlet.PropertyTable) == before
        assert {f.Tag for f in sim.FieldManager.Fields} == fields
        _, status = session.Parts.SetDisplay(original_display, False, False)
        if status:
            status.Dispose()
        session.Parts.SetWork(original_work)
    assert {p.FullPath: bool(p.IsModified) for p in session.Parts} == original_flags
    result.update(
        outer_rollback_verified=True,
        original_flags_preserved=True,
        boundary_descriptor=inlet.DescriptorName,
        solver_launched=False,
    )
    return result

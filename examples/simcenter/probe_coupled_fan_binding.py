"""Bounded coupled fan/head-loss authoring probe; no save, export or solve."""


def run(executor):
    from nx_mcp.simcenter.fan_boundary import binding
    from nx_mcp.simcenter.fan_field import create_fan_table
    from nx_mcp.simcenter.head_loss import require_manual_dynamic_pressure
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    session, nx = executor.session, executor.nxopen
    original_work, original_display = session.Parts.BaseWork, session.Parts.BaseDisplay
    flags = {p.FullPath: bool(p.IsModified) for p in session.Parts}
    matches = [
        p
        for p in session.Parts
        if "E-finned-material-control-export-20260908-r1" in p.FullPath
        and p.FullPath.endswith(".sim")
    ]
    if len(matches) != 1:
        raise ValueError("Expected one loaded isolated finned material-control fixture")
    sim = matches[0]
    solution = sim.Simulation.ActiveSolution
    assert solution.AnalysisType == "Coupled Thermal-Flow"
    (inlet,) = [b for b in sim.Simulation.SimulationObjects if b.DescriptorName == "Inlet"]
    (opening,) = [b for b in sim.Simulation.SimulationObjects if b.DescriptorName == "Opening"]
    before = binding(inlet.PropertyTable)
    old_loss = opening.PropertyTable.GetNamedPropertyTablePropertyValue("Head Loss")
    ambient = solution.PropertyTable.GetScalarWithDataPropertyValue("Fluid Temperature")
    fields = {f.Tag for f in sim.FieldManager.Fields}
    tables = {t.Tag for t in sim.ModelingObjectPropertyTables}
    _, status = session.Parts.SetDisplay(sim, False, False)
    if status:
        status.Dispose()
    session.Parts.SetWork(sim)
    sim.ModelingViews.WorkView.Fit()
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "Coupled fan binding probe")
    result = {"fixture": sim.FullPath, "analysis_type": solution.AnalysisType}
    try:
        table = create_fan_table(
            session,
            sim,
            {
                "name": "MCP reversible coupled fan probe",
                "pressure_convention": "static",
                "rpm": 1000,
                "reference_density_kg_m3": 1.2,
                "points": [
                    {"flow_m3_s": 0, "pressure_Pa": 1},
                    {"flow_m3_s": 0.0004, "pressure_Pa": 0},
                ],
                "stall_region": "Synthetic authoring probe only",
                "provenance": {"kind": "assumed", "source": "Coupled API binding probe"},
            },
        )["table"]
        wrapper = sim.FieldManager.CreateScalarFieldWrapperWithField(table, 1.0)
        inlet.PropertyTable.SetScalarFieldWrapperPropertyValue("Fan Curve", wrapper)
        inlet.PropertyTable.SetIntegerPropertyValue("Mode Option", 5)
        result["fan_binding"] = binding(inlet.PropertyTable)
        assert result["fan_binding"] == {
            "mode": 5,
            "field_tag": int(table.Tag),
            "scale_factor": 1.0,
        }
        loss = sim.ModelingObjectPropertyTables.CreateModelingObjectPropertyTable(
            "Head Loss",
            "NX MULTIPHYSICS - Coupled Thermal-Flow",
            "NX MULTIPHYSICS",
            "MCP reversible coupled loss probe",
            0,
        )
        p = loss.PropertyTable
        p.SetIntegerPropertyValue("Type", 0)
        p.SetIntegerPropertyValue("Proportional to", 0)
        result["loss_selectors"] = require_manual_dynamic_pressure(loss)
        _, unit = p.GetBaseScalarWithDataPropertyValue("Head Loss Coefficient")
        p.SetBaseScalarWithDataPropertyValue("Head Loss Coefficient", 2.0, unit)
        opening.PropertyTable.SetNamedPropertyTablePropertyValue("Head Loss", loss)
        assert opening.PropertyTable.GetNamedPropertyTablePropertyValue("Head Loss") == loss
        assert p.GetBaseScalarWithDataPropertyValue("Head Loss Coefficient") == (2.0, unit)
        result["loss_coefficient"] = 2.0
        result["loss_units"] = unit.Name if unit else "dimensionless"
        assert solution.PropertyTable.GetScalarWithDataPropertyValue("Fluid Temperature") == ambient
        result["authoring_passed"] = True
    finally:
        session.UndoToMark(mark, None)
        session.DeleteUndoMark(mark, None)
        assert binding(inlet.PropertyTable) == before
        assert opening.PropertyTable.GetNamedPropertyTablePropertyValue("Head Loss") == old_loss
        assert {f.Tag for f in sim.FieldManager.Fields} == fields
        assert {t.Tag for t in sim.ModelingObjectPropertyTables} == tables
        _, status = session.Parts.SetDisplay(original_display, False, False)
        if status:
            status.Dispose()
        session.Parts.SetWork(original_work)
        original_display.ModelingViews.WorkView.Fit()
    assert {p.FullPath: bool(p.IsModified) for p in session.Parts} == flags
    result.update(
        rollback_verified=True,
        original_flags_preserved=True,
        solver_launched=False,
        exported=False,
        numerical_acceptance=False,
    )
    return result

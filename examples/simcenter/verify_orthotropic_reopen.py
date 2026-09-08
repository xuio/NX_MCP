"""Save and fully unload/reopen the isolated orthotropic SIM and FEM."""


def run(executor):
    from nx_mcp.runtime import NXToolError
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    s, nx = executor.session, executor.nxopen
    sim = s.Parts.BaseWork
    expected = executor.workspace.resolve(
        "ui-benchmarks/orthotropic-solve-20260908-r1/orthotropic_solve_r1.sim"
    )
    assert executor.workspace.resolve(sim.FullPath) == expected
    fem = sim.FemPart
    fem_path = fem.FullPath
    others = {p.FullPath: bool(p.IsModified) for p in s.Parts if p not in (sim, fem)}
    sim_id = executor._reference(sim, "part", sim, "part")["id"]
    fem_id = executor._reference(fem, "part", fem, "part")["id"]
    temperature_before = executor._sim_temperature_result(sim_id)
    saved = executor._sim_save(sim_id)
    assert not sim.IsModified and not fem.IsModified
    sim_closed = executor._sim_close(sim_id)
    fem_closed = executor._sim_close(fem_id)
    assert not any(p.FullPath in (str(expected), fem_path) for p in s.Parts)
    opened = executor._sim_open(str(expected))
    sim = s.Parts.BaseWork
    fem = sim.FemPart
    assert fem.FullPath == fem_path
    stale = []
    for old in (sim_id, fem_id):
        try:
            executor.objects.resolve(old, expected_kind="part")
        except NXToolError as error:
            stale.append(error.code)
        else:
            raise ValueError("Closed document reference unexpectedly resolved")
    material = next(
        m for m in fem.MaterialManager.PhysicalMaterials if m.Name == "ORTHOTROPIC_STUDY_12_7_04"
    )
    values = {}
    expected_values = {
        "ThermalConductivity": 12,
        "ThermalConductivity2": 7,
        "ThermalConductivity3": 0.4,
        "MassDensity": 1900,
        "SpecificHeat": 900,
    }
    for key, value in expected_values.items():
        expression = material.GetPropTable().GetScalarFieldWrapperPropertyValue(key).GetExpression()
        actual = expression.GetValueUsingUnits(nx.Expression.UnitsOption.Expression)
        assert abs(actual - value) < 1e-10
        values[key] = {"value": actual, "unit": expression.Units.Name}
    collectors = fem.BaseFEModel.MeshManager.GetMeshCollectors()
    assert len(collectors) == 1
    table = (
        collectors[0]
        .ElementPropertyTable.GetNamedPropertyTablePropertyValue("Solid Property")
        .PropertyTable
    )
    assignment = table.GetPhysicalMaterialPropertyValue("material")
    try:
        assert assignment.Material == material and not assignment.MaterialInherited
    finally:
        assignment.Dispose()
    temperature_after = executor._sim_temperature_result(opened["document"]["id"])
    for key in ("minimum", "maximum", "node_count", "units"):
        assert temperature_after[key] == temperature_before[key]
    after_flags = {p.FullPath: bool(p.IsModified) for p in s.Parts}
    assert all(after_flags.get(path) == flag for path, flag in others.items())
    shown = executor._sim_show_temperature(
        opened["document"]["id"], name="Reopened orthotropic temperature"
    )
    s.ListingWindow.CloseWindow()
    sim.ModelingViews.WorkView.Fit()
    return {
        "saved": saved,
        "closed": [sim_closed, fem_closed],
        "opened": opened,
        "stale_reference_errors": stale,
        "material_properties": values,
        "assignment_preserved": True,
        "temperature_before": temperature_before,
        "temperature_after": temperature_after,
        "view": shown,
        "unrelated_flags_preserved": True,
        "both_documents_fully_unloaded": True,
        "solver_launched": False,
    }

"""Bounded small-mesh test of the documented Ambient Pressure selector."""


def run(executor):
    import json
    import xml.etree.ElementTree as ET

    import NXOpen as nx

    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    s = executor.session
    matches = [
        p
        for p in s.Parts
        if "E-finned-tight-20260908-r1" in p.FullPath and p.FullPath.endswith(".sim")
    ]
    if len(matches) != 1:
        raise ValueError("Expected loaded retained 2 mm tight-control fixture")
    root = executor.workspace.resolve("ui-benchmarks/E-finned-pressure-20260908-r1")
    receipt = executor.workspace.resolve("ui-benchmarks/E-finned-pressure-r1.json")
    if root.exists() or receipt.exists():
        raise ValueError("Inspect existing diagnostic; never replay a launch")
    rows = {
        "job_id": "coupled-finned-pressure-r1",
        "physical_acceptance": False,
        "mesh_changed": False,
    }

    def record(key, value):
        rows[key] = value
        receipt.write_text(json.dumps(rows, indent=2))

    sim = matches[0]
    _, status = s.Parts.SetDisplay(sim, False, False)
    if status:
        status.Dispose()
    s.Parts.SetWork(sim)
    def ref():
        return executor._reference(sim, "part", sim, "SIM")["id"]
    record("copy", executor._sim_save_as(ref(), str(root / "finned_pressure_r1.sim")))
    solution = sim.Simulation.ActiveSolution
    mark = s.SetUndoMark(nx.Session.MarkVisibility.Visible, "MCP specified-pressure diagnostic")
    try:
        props = solution.PropertyTable
        expression = sim.Expressions.CreateSystemNumberExpression(
            "101325", sim.UnitCollection.FindObject("PressurePascals")
        )
        wrapper = sim.FieldManager.CreateScalarFieldWrapperWithExpression(expression)
        props.SetScalarFieldWrapperPropertyValue("Absolute Pressure", wrapper)
        props.SetIntegerPropertyValue("Ambient Pressure", 0)
        assert props.GetIntegerPropertyValue("Ambient Pressure") == 0
        actual = props.GetScalarFieldWrapperPropertyValue("Absolute Pressure").GetExpression()
        assert actual.Units.Name == "PressurePascals"
        assert actual.GetValueUsingUnits(nx.Expression.UnitsOption.Expression) == 101325
        for table, key in [
            ("Thermal Parameters", "Thermal Steady State - Iteration Limit"),
            ("Flow Solution Parameters", "3D Flow Steady State - Iteration Limit"),
        ]:
            p = props.GetNamedPropertyTablePropertyValue(table).PropertyTable
            p.SetIntegerPropertyValue(key, 100)
            assert p.GetIntegerPropertyValue(key) == 100
        output = props.GetNamedPropertyTablePropertyValue(
            "Thermal-Flow Output Requests"
        ).PropertyTable
        for key in ("Fluid Densities", "Mass Fluxes"):
            output.SetBooleanPropertyValue(key, True)
            assert output.GetBooleanPropertyValue(key)
        record(
            "native_controls",
            {
                "ambient_pressure_mode": 0,
                "absolute_pressure_Pa": 101325,
                "iteration_limits": 100,
                "density_and_mass_flux_output": True,
            },
        )
    except Exception:
        s.UndoToMark(mark, None)
        raise
    record("save", executor._sim_save(ref()))
    prepared = executor._sim_prepare_solve(ref(), rows["job_id"])
    record("prepare", prepared)
    xml = ET.parse(prepared["input_path"]).getroot()
    assert xml.findtext("./Units/System") == "Millimeters"
    values = xml.findall("./SolutionParameters/Solution/Property[@name='Ambient Pressure']/Value")
    if not values:
        values = xml.findall(".//Property[@name='Ambient Pressure']/Value")
    assert len(values) == 1 and int(values[0].text) == 0
    pressure = xml.findall(".//Property[@name='Absolute Pressure']/Value")
    assert len(pressure) == 1 and abs(float(pressure[0].text) - 101.325) < 1e-7
    record("exported_pressure", {"mode": 0, "pressure_mN_per_mm2": 101.325})
    record("launch_intent", "Observe this durable job after interruption; never duplicate")
    record("launch", executor._sim_launch(ref(), rows["job_id"]))
    return rows

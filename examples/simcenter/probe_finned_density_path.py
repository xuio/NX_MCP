"""Bounded diagnostic: documented buoyancy flag with no gravity load."""


def run(executor):
    import json
    import xml.etree.ElementTree as ET

    import NXOpen as nx

    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    s = executor.session
    root = executor.workspace.resolve("ui-benchmarks/E-finned-density-path-20260908-r1")
    receipt = executor.workspace.resolve("ui-benchmarks/E-finned-density-path-r1.json")
    if root.exists() or receipt.exists():
        raise ValueError("Inspect existing diagnostic; do not repeat a mutation or launch")
    source = executor.workspace.resolve(
        "ui-benchmarks/E-finned-tight-20260908-r1/finned_tight_r1.sim"
    )
    rows = {
        "job_id": "coupled-finned-density-path-r1",
        "physical_acceptance": False,
        "mesh_changed": False,
    }

    def record(key, value):
        rows[key] = value
        receipt.write_text(json.dumps(rows, indent=2))

    record("open_source", executor._sim_open(str(source)))
    sim = s.Parts.BaseWork

    def ref():
        return executor._reference(sim, "part", sim, "SIM")["id"]

    record("copy", executor._sim_save_as(ref(), str(root / "finned_density_path_r1.sim")))
    solution = sim.Simulation.ActiveSolution
    loads = [b.DescriptorName for b in sim.Simulation.Loads]
    if any("gravity" in name.casefold() for name in loads):
        raise ValueError("No gravity load allowed in this diagnostic")
    mark = s.SetUndoMark(nx.Session.MarkVisibility.Visible, "MCP density path diagnostic")
    try:
        props = solution.PropertyTable
        if props.GetIntegerPropertyValue("Ambient Pressure") != 1:
            raise ValueError("Preserve the existing altitude pressure route")
        props.SetBooleanPropertyValue("Buoyancy", True)
        if not props.GetBooleanPropertyValue("Buoyancy"):
            raise ValueError("Buoyancy flag readback differs")
        for table, key in [
            ("Thermal Parameters", "Thermal Steady State - Iteration Limit"),
            ("Flow Solution Parameters", "3D Flow Steady State - Iteration Limit"),
        ]:
            p = props.GetNamedPropertyTablePropertyValue(table).PropertyTable
            p.SetIntegerPropertyValue(key, 100)
            if p.GetIntegerPropertyValue(key) != 100:
                raise ValueError("Iteration-limit readback differs")
        output = props.GetNamedPropertyTablePropertyValue(
            "Thermal-Flow Output Requests"
        ).PropertyTable
        for key in ("Fluid Densities", "Mass Fluxes"):
            output.SetBooleanPropertyValue(key, True)
            if not output.GetBooleanPropertyValue(key):
                raise ValueError("Output readback differs")
        record(
            "native_controls",
            {
                "buoyancy": True,
                "gravity_loads": [],
                "iteration_limit": 100,
                "ambient_pressure_mode": 1,
            },
        )
    except Exception:
        s.UndoToMark(mark, None)
        raise
    record("save", executor._sim_save(ref()))
    prepared = executor._sim_prepare_solve(ref(), rows["job_id"])
    record("prepare", prepared)
    xml = ET.parse(prepared["input_path"]).getroot()
    flags = xml.findall(".//Property[@name='Buoyancy']/Value")
    if len(flags) != 1 or int(flags[0].text) != 1:
        raise ValueError("Exported buoyancy flag differs")
    if xml.findall(".//Gravity"):
        raise ValueError("Unexpected exported gravity load")
    record(
        "export_checks",
        {"buoyancy": 1, "gravity_loads": [], "temperature_and_pressure_guards": "passed"},
    )
    record("launch_intent", "Observe this existing durable job after interruption; never duplicate")
    record("launch", executor._sim_launch(ref(), rows["job_id"]))
    return rows

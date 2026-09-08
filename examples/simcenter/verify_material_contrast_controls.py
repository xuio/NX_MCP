"""Export-only correction of the bounded contrast fixture; never reruns its solve."""


def run(executor):
    import json
    import xml.etree.ElementTree as ET

    import NXOpen as nx

    from nx_mcp.simcenter.input_export import export_flow_input
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    session = executor.session
    sim = session.Parts.BaseWork
    if "E-finned-material-contrast-run-20260908-r1" not in sim.FullPath:
        raise ValueError("Requires the retained terminal contrast diagnostic")
    root = executor.workspace.resolve("ui-benchmarks/E-finned-material-control-export-20260908-r1")
    if root.exists():
        raise ValueError("Inspect existing export; never replay the mutation")
    executor._sim_save_as(
        executor._reference(sim, "part", sim, "SIM")["id"], str(root / "control_export.sim")
    )
    solution = sim.Simulation.ActiveSolution
    changes = [
        ("Thermal Parameters", "Thermal Steady State - Iteration Limit", 100),
        ("Flow Solution Parameters", "3D Flow Steady State - Iteration Limit", 100),
        ("Thermal-Flow Output Requests", "Fluid Densities", True),
        ("Thermal-Flow Output Requests", "Mass Fluxes", True),
    ]
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "MCP contrast control correction")
    try:
        for table, key, value in changes:
            props = solution.PropertyTable.GetNamedPropertyTablePropertyValue(table).PropertyTable
            setter = (
                props.SetBooleanPropertyValue
                if type(value) is bool
                else props.SetIntegerPropertyValue
            )
            getter = (
                props.GetBooleanPropertyValue
                if type(value) is bool
                else props.GetIntegerPropertyValue
            )
            setter(key, value)
            if getter(key) != value:
                raise ValueError("Committed control differs: " + key)
    except Exception:
        session.UndoToMark(mark, None)
        raise
    executor._sim_save(executor._reference(sim, "part", sim, "SIM")["id"])
    exported = export_flow_input(session, executor.workspace, sim)
    xml = ET.parse(exported["input_path"]).getroot()
    for _, key, value in changes:
        rows = xml.findall(".//Property[@name='" + key + "']/Value")
        if len(rows) != 1 or int(rows[0].text) != int(value):
            raise ValueError("Exported control differs: " + key)
    result = {
        "controls": changes,
        "native_and_xml_match": True,
        "export": exported,
        "solver_launched": False,
        "prior_results_reused_for_acceptance": False,
        "limitation": "Prior contrast run used default 500-iteration cap, exited at 14; corrected export is not a rerun.",
    }
    (root / "verification.json").write_text(json.dumps(result, indent=2))
    return result

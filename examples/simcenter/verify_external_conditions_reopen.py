"""Save/reopen/export an isolated copy; preserve the original completed diagnostic."""


def run(executor):
    import json
    import runpy
    import shutil
    import time
    import xml.etree.ElementTree as ET

    from nx_mcp.simcenter.input_export import export_flow_input
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    sim = executor.session.Parts.BaseWork
    if "E-external-diagnostic-20260908-r1" not in sim.FullPath:
        raise ValueError("Activate the retained diagnostic source")
    root = executor.workspace.resolve("ui-benchmarks/E-external-reopen-20260908-r1")
    receipt = executor.workspace.resolve("ui-benchmarks/E-external-reopen-r1.json")
    if root.exists() or receipt.exists():
        raise ValueError("Inspect existing receipt; never repeat lifecycle mutation blindly")
    audit = runpy.run_path(
        r"Z:\nx-mcp-integration\simcenter-discovery\audit_coupled_effective_inputs.py"
    )["run"]
    rows = {"solver_launched": False, "numerical_acceptance": False}
    started = time.monotonic()

    def record(key, value):
        rows[key] = value
        receipt.write_text(json.dumps(rows, indent=2))

    record(
        "copy",
        executor._sim_save_as(
            executor._reference(sim, "part", sim, "SIM")["id"],
            str(root / "coupled_external_reopen_r1.sim"),
        ),
    )
    record("before_close", audit(executor))
    path = sim.FullPath
    record("close", executor._sim_close(executor._reference(sim, "part", sim, "SIM")["id"]))
    record("open", executor._sim_open(path))
    sim = executor.session.Parts.BaseWork
    record("after_reopen", audit(executor))
    # Ignore transport metadata; compare the actual native observations.
    keys = (
        "solution",
        "steps",
        "document_boundaries",
        "solution_fields",
        "ambient_pressure_mode",
        "tables",
    )
    equal = {key: rows["before_close"][key] == rows["after_reopen"][key] for key in keys}
    record("readback_equal", equal)
    assert all(equal.values()), equal
    exported = export_flow_input(executor.session, executor.workspace, sim)
    record("export", exported)
    xml = ET.parse(exported["input_path"]).getroot()
    conditions = xml.findall(".//ExternalCondition")
    assert len(conditions) == 1
    condition = conditions[0]
    values = {p.attrib["name"]: p.findtext("Value") for p in condition.findall("Property")}
    assert int(values["Temperature Option"]) == 0
    assert float(values["Temperature Value"]) == 20
    boundaries = [
        b for b in xml.findall(".//FlowBc") if b.attrib.get("type") in ("Inlet", "Opening")
    ]
    assert len(boundaries) == 2
    bindings = []
    for boundary in boundaries:
        refs = boundary.findall("Property[@name='Inlet Conditions']/Value")
        assert len(refs) == 1 and refs[0].text.strip() == condition.attrib["uid"]
        bindings.append({"name": boundary.attrib["uname"], "condition_uid": refs[0].text.strip()})
    record(
        "external_export", {"temperature_c": 20, "mode": "specified", "boundary_bindings": bindings}
    )
    shutil.copyfile(
        exported["input_path"],
        r"Z:\nx-mcp-integration\simcenter-discovery\coupled-external-reopen-deck.xml",
    )
    record("elapsed_seconds", time.monotonic() - started)
    record("persistence_export_passed", True)
    return rows

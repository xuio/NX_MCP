"""Verify input and result persistence on the isolated, terminal finned fixture."""


def run(executor):
    import hashlib
    import json
    import runpy
    import shutil
    import time
    import xml.etree.ElementTree as ET
    from pathlib import Path

    from nx_mcp.simcenter.input_export import export_flow_input
    from nx_mcp.simcenter.results import temperature_extrema
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    s = executor.session
    sim = s.Parts.BaseWork
    if "E-finned-layer-extended-20260908-r1" not in sim.FullPath:
        raise ValueError("Activate the terminal isolated finned run")
    source = Path(sim.FullPath)
    root = executor.workspace.resolve("ui-benchmarks/E-finned-layer-lifecycle-20260908-r1")
    export_root = executor.workspace.resolve(
        "ui-benchmarks/E-finned-layer-reopen-export-20260908-r1"
    )
    if root.exists() or export_root.exists():
        raise ValueError("Inspect existing lifecycle receipt; do not replay mutations")
    root.mkdir()
    receipt = root / "receipt.json"
    rows = {"physical_acceptance": False, "solver_launched": False}
    started = time.monotonic()
    audit_module = runpy.run_path(
        r"Z:\nx-mcp-integration\simcenter-discovery\audit_coupled_effective_inputs.py"
    )
    audit, validate = audit_module["run"], audit_module["validate_finned_snapshot"]

    def record(key, value):
        rows[key] = value
        receipt.write_text(json.dumps(rows, indent=2))

    def ref(part):
        return executor._reference(part, "part", part, "SIM")["id"]

    def unrelated():
        return {p.FullPath: bool(p.IsModified) for p in s.Parts if p.FullPath != str(source)}

    def results(part):
        return {
            location: temperature_extrema(s, part, location=location)
            for location in ("nodal", "elemental", "element_nodal")
        }

    def file_hash(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    record("unrelated_before", unrelated())
    files = sorted(list(source.parent.glob("*.xml")) + list(source.parent.glob("*.bun")))
    if len(files) != 2:
        raise ValueError("Expected one input and one result file")
    record("files_before", {str(p): file_hash(p) for p in files})
    shutil.copy2(source, root / "analysis-before-save.sim.backup")
    record("before", audit(executor))
    record("before_validation", validate(rows["before"]))
    record("results_before", results(sim))
    record("save", executor._sim_save(ref(sim)))
    record("close", executor._sim_close(ref(sim)))
    record("open", executor._sim_open(str(source)))
    sim = s.Parts.BaseWork
    record("after", audit(executor))
    record("after_validation", validate(rows["after"]))
    keys = (
        "solution",
        "steps",
        "document_boundaries",
        "solution_fields",
        "ambient_pressure_mode",
        "tables",
    )
    equal = {key: rows["before"][key] == rows["after"][key] for key in keys}
    record("native_state_equal", equal)
    if not all(equal.values()):
        raise ValueError("Native state changed across save/reopen")
    record("results_after", results(sim))
    record("results_equal", rows["results_before"] == rows["results_after"])
    if not rows["results_equal"]:
        raise ValueError("Result readback changed across save/reopen")
    record("unrelated_after", unrelated())
    if rows["unrelated_after"] != rows["unrelated_before"]:
        raise ValueError("Unrelated part inventory/modified flags changed")
    record(
        "copy", executor._sim_save_as(ref(sim), str(export_root / "finned_reopen_export_r1.sim"))
    )
    exported = export_flow_input(s, executor.workspace, s.Parts.BaseWork)
    record("export", exported)
    xml = ET.parse(exported["input_path"]).getroot()
    conditions = xml.findall(".//ExternalCondition")
    if len(conditions) != 1:
        raise ValueError("Expected one external conditions table")
    condition = conditions[0]
    if float(condition.findtext("Property[@name='Temperature Value']/Value")) != 20.0:
        raise ValueError("Exported external temperature differs")
    if int(condition.findtext("Property[@name='Temperature Option']/Value")) != 0:
        raise ValueError("Exported temperature selector differs")
    bcs = [b for b in xml.iter("FlowBc") if b.get("type") in ("Inlet", "Opening")]
    if len(bcs) != 2 or any(
        b.findtext("Property[@name='Inlet Conditions']/Value").strip() != condition.get("uid")
        for b in bcs
    ):
        raise ValueError("Exported inlet/opening bindings differ")
    record("files_after", {str(p): file_hash(p) for p in files})
    if rows["files_before"] != rows["files_after"]:
        raise ValueError("Source solver input or result changed")
    record("persistence_verified", True)
    record("elapsed_seconds", time.monotonic() - started)
    return rows

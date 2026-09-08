"""Prepare a 1 W two-block contact benchmark; save/export only, never solve."""


def run(executor):
    import json, shutil, time
    from pathlib import Path
    from nx_mcp.simcenter.solver_guard import require_solver_idle
    from nx_mcp.simcenter.selections import face_inventory
    from nx_mcp.simcenter.input_export import export_flow_input

    require_solver_idle()
    sim = executor.session.Parts.BaseWork
    if "B-contact-authoring-20260909-r1" not in sim.FullPath:
        raise ValueError("Expected isolated contact fixture")
    fem = sim.FemPart
    report = Path(r"Z:\nx-mcp-integration\simcenter-discovery\contact-resistance-preparation.json")
    if report.exists():
        raise ValueError("Inspect retained preparation before retrying")
    receipt = {
        "stages": {},
        "solver_launched": False,
        "inputs": {
            "power_w": 1.0,
            "conductivity_w_m_k": 200.0,
            "block_length_mm": 10.0,
            "cross_section_mm2": 100.0,
            "contact_resistance_k_w": 0.5,
            "fixed_temperature_k": 293.15,
        },
        "expected": {
            "interface_drop_k": 0.5,
            "maximum_temperature_k": 294.4,
            "heat_rejection_w": 1.0,
        },
    }
    flags = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts if p not in (sim, fem)}

    def stage(name, fn):
        started = time.monotonic()
        try:
            result = fn()
        except Exception as e:
            receipt["failed_stage"] = name
            receipt["error"] = {"message": str(e), "details": getattr(e, "details", {})}
            report.write_text(json.dumps(receipt, indent=2))
            raise
        receipt["stages"][name] = {"elapsed_seconds": time.monotonic() - started, "result": result}
        report.write_text(json.dumps(receipt, indent=2))
        return result

    sid = executor._reference(sim, "part", sim, "SIM")["id"]
    fid = executor._reference(fem, "part", fem, "FEM")["id"]
    stage("mesh", lambda: executor._sim_mesh(fid, size_mm=5.0))
    stage(
        "material",
        lambda: executor._sim_material(
            fid, "CONTACT_K200", 200.0, 2700.0, 900.0, "Assumed generic analytical constants", True
        ),
    )
    stage("save_fem", lambda: executor._sim_save(fid))
    stage("activate_sim", lambda: executor._sim_activate(sid))
    rows = face_inventory(executor.session, sim)["rows"]
    left = [
        r
        for r in rows
        if abs(r["bounds"]["minimum"][0]) < 1e-6 and abs(r["bounds"]["maximum"][0]) < 1e-6
    ]
    right = [
        r
        for r in rows
        if abs(r["bounds"]["minimum"][0] - 20) < 1e-6 and abs(r["bounds"]["maximum"][0] - 20) < 1e-6
    ]
    assert len(left) == len(right) == 1
    body = executor._reference(left[0]["body"], "body", fem, "body")["id"]
    face = executor._reference(right[0]["face"], "face", sim, "face")["id"]
    stage(
        "power",
        lambda: executor._sim_heat_power(
            sid,
            body,
            1.0,
            "CONTACT_INTERNAL_1W",
            "Uniform generation in left block only; analytical Tmax=294.4 K",
        ),
    )
    stage(
        "temperature",
        lambda: executor._sim_temperature(
            sid,
            [face],
            293.15,
            "CONTACT_SINK",
            "Fixed right end; all other exterior faces adiabatic",
        ),
    )
    stage("save_sim", lambda: executor._sim_save(sid))
    root = executor.workspace.resolve("ui-benchmarks/B-contact-resistance-export-20260909-r1")
    root.mkdir()
    path = root / "contact_resistance_r1.sim"
    shutil.copy2(sim.FullPath, path)
    stage("open_export_copy", lambda: executor._sim_open(str(path)))
    copy = executor.session.Parts.BaseWork
    cid = executor._reference(copy, "part", copy, "SIM")["id"]
    stage("save_export_copy", lambda: executor._sim_save(cid))
    exported = stage(
        "export", lambda: export_flow_input(executor.session, executor.workspace, copy)
    )
    shutil.copy2(
        exported["input_path"],
        Path(r"Z:\nx-mcp-integration\simcenter-discovery\contact-resistance.xml"),
    )
    after = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    assert all(after[p] == v for p, v in flags.items())
    receipt["unrelated_modified_flags_preserved"] = True
    report.write_text(json.dumps(receipt, indent=2))
    return receipt

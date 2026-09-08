"""Export a native manual head-loss fixture; never execute the solver."""


def run(executor):
    import json
    import shutil
    from pathlib import Path

    from nx_mcp.simcenter.head_loss import set_opening_head_loss
    from nx_mcp.simcenter.input_export import export_flow_input
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    root = executor.workspace.resolve("ui-benchmarks/F3-head-loss-export-20260909-r1")
    if root.exists():
        raise ValueError("Inspect retained export before retry")
    root.mkdir()
    flags = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    source = executor.workspace.resolve("ui-benchmarks/D-head-loss-mcp-20260908-r1/head_loss_test_r1.sim")
    path = root / "f3_head_loss_export_r1.sim"
    shutil.copy2(source, path)
    executor._sim_open(str(path))
    sim = executor.session.Parts.BaseWork
    opening = next(b for b in sim.Simulation.SimulationObjects if b.DescriptorName == "Opening")
    props = opening.PropertyTable.GetNamedPropertyTablePropertyValue("Head Loss").PropertyTable
    old, _ = props.GetBaseScalarWithDataPropertyValue("Head Loss Coefficient")
    authored = set_opening_head_loss(executor.session, sim, opening, 2.0, expected_coefficient=old)
    assert authored["selectors"] == {"Type": 0, "Proportional to": 0}
    executor._sim_save(executor._reference(sim, "part", sim, "SIM")["id"])
    exported = export_flow_input(executor.session, executor.workspace, sim)
    files = list(root.glob("*.xml"))
    assert len(files) == 1
    raw = files[0].read_text()
    snippets = [line for line in raw.splitlines() if "loss" in line.lower() or "Duct Opening" in line]
    after = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    assert all(after.get(p) == modified for p, modified in flags.items())
    result = {"native_readback": authored, "export": exported, "xml_path": str(files[0]),
              "loss_lines": snippets, "export_completed": True, "export_semantics_verified": False,
              "unrelated_modified_flags_preserved": True, "solver_launched": False}
    Path(r"Z:\nx-mcp-integration\simcenter-discovery\head-loss-export.json").write_text(json.dumps(result, indent=2))
    shutil.copy2(files[0], Path(r"Z:\nx-mcp-integration\simcenter-discovery\head-loss-export.xml"))
    return result

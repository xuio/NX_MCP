"""Prepare isolated selector fixtures; all edits confined to copied SIM files."""


def run(executor):
    import importlib
    import json
    import shutil
    from pathlib import Path

    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    importlib.reload(importlib.import_module("nx_mcp.simcenter.head_loss"))
    root = executor.workspace.resolve("ui-benchmarks/F3-public-selector-20260908-r1")
    if root.exists():
        raise ValueError("Inspect retained fixtures before retry")
    root.mkdir()
    original = executor.session.Parts.BaseWork
    flags = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    source = executor.workspace.resolve(
        "ui-benchmarks/D-head-loss-mcp-20260908-r1/head_loss_test_r1.sim"
    )
    cases = []
    for index, (mode, proportional) in enumerate([(1, 0), (0, 1), (0, 0)]):
        path = root / ("f3_public_selector_r1_" + str(index) + ".sim")
        shutil.copy2(source, path)
        result = executor._sim_open(str(path))
        sim = executor.session.Parts.BaseWork
        candidates = [
            b
            for b in sim.Simulation.SimulationObjects
            if b.DescriptorName == "Opening"
            and b.PropertyTable.GetNamedPropertyTablePropertyValue("Head Loss") is not None
        ]
        assert len(candidates) == 1
        boundary = candidates[0]
        props = boundary.PropertyTable.GetNamedPropertyTablePropertyValue("Head Loss").PropertyTable
        coefficient, unit = props.GetBaseScalarWithDataPropertyValue("Head Loss Coefficient")
        props.SetIntegerPropertyValue("Type", mode)
        props.SetIntegerPropertyValue("Proportional to", proportional)
        assert props.GetIntegerPropertyValue("Type") == mode
        assert props.GetIntegerPropertyValue("Proportional to") == proportional
        cases.append(
            {
                "document": result["document"]["id"],
                "path": str(path),
                "opening": executor._reference(boundary, "simulation_object", sim, "opening")["id"],
                "coefficient": coefficient,
                "selectors": [mode, proportional],
            }
        )
    after = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    assert all(after.get(path) == flag for path, flag in flags.items())
    context = {
        "cases": cases,
        "original_work_path": original.FullPath,
        "original_flags": flags,
        "solver_launched": False,
    }
    Path(r"Z:\nx-mcp-integration\simcenter-discovery\head-loss-public-context.json").write_text(
        json.dumps(context)
    )
    return context

"""Probe selector value 1 in an isolated saved frame study; do not solve."""


def run(executor):
    import json
    import shutil
    import xml.etree.ElementTree as ET

    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    s, nx = executor.session, executor.nxopen
    sim = s.Parts.BaseWork
    assert sim.FullPath.endswith("rotated_ortho_export_r1.sim")
    fem = sim.FemPart
    assert fem.FullPath.endswith("RotatedOrthoR1_mesh.fem")
    assert not sim.IsModified and not fem.IsModified
    output = executor.workspace.resolve("ui-benchmarks/orthotropic-selector-one-20260908-r1")
    assert not output.exists()
    fem_path = executor.workspace.resolve(fem.FullPath)
    marker = fem_path.parent / "selector-one-intent.json"
    with marker.open("x") as stream:
        json.dump({"value_to_probe": 1, "state": "accepted", "retry_allowed": False}, stream)
    shutil.copy2(fem_path, fem_path.with_suffix(".before-selector-one.fem"))
    before = {p.FullPath: bool(p.IsModified) for p in s.Parts if p not in (sim, fem)}
    sim_id = executor._reference(sim, "part", sim, "part")["id"]
    fem_id = executor._reference(fem, "part", fem, "part")["id"]
    executor._sim_activate(fem_id)
    collectors = fem.BaseFEModel.MeshManager.GetMeshCollectors()
    assert len(collectors) == 1
    table = (
        collectors[0]
        .ElementPropertyTable.GetNamedPropertyTablePropertyValue("Solid Property")
        .PropertyTable
    )
    assert table.GetIntegerPropertyValue("material orientation type") == 0
    frame = table.GetCoordinateSystemPropertyValue("material orientation")
    assert frame is not None
    mark = s.SetUndoMark(
        nx.Session.MarkVisibility.Visible, "Probe explicit material orientation selector"
    )
    try:
        table.SetIntegerPropertyValue("material orientation type", 1)
        assert table.GetIntegerPropertyValue("material orientation type") == 1
        assert table.GetCoordinateSystemPropertyValue("material orientation") == frame
    except Exception:
        s.UndoToMark(mark, None)
        s.DeleteUndoMark(mark, None)
        raise
    saved = executor._sim_save(fem_id)
    executor._sim_activate(sim_id)
    copied = executor._sim_save_as(sim_id, str(output / "selector_one_r1.sim"))
    result = executor._sim_export_input(copied["document"]["id"])
    root = ET.parse(result["input_path"]).getroot()
    sections = {
        key: ET.tostring(root.find(key), encoding="unicode")[:20000]
        for key in ("PhysicalPropertyTableList", "Alignments", "ElementAssociatedDataList")
        if root.find(key) is not None
    }
    assert all(
        {p.FullPath: bool(p.IsModified) for p in s.Parts}.get(path) == flag
        for path, flag in before.items()
    )
    return {
        "selector_readback": 1,
        "saved": saved,
        "export": result,
        "sections": sections,
        "source_flags_preserved": True,
        "selector_meaning": "awaiting_export_interpretation",
        "solver_launched": False,
    }

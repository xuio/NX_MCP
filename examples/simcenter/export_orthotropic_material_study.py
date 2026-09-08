"""Assign synthetic orthotropy in an independent benchmark and inspect export."""


def run(executor):
    import json
    import shutil
    import xml.etree.ElementTree as ET

    from nx_mcp.simcenter.directional_material import create_orthotropic
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    s = executor.session
    sim = s.Parts.BaseWork
    if not sim.FullPath.endswith("OrthotropicR1_analysis.sim"):
        raise ValueError("Requires the independent orthotropic study")
    fem = sim.FemPart
    if sim.IsModified or fem.IsModified:
        raise ValueError("Study must be saved before this one-shot fixture")
    folder = executor.workspace.resolve(sim.FullPath).parent
    marker = folder / "orthotropic-assignment-intent.json"
    with marker.open("x") as stream:
        json.dump({"state": "accepted", "retry_allowed": False}, stream)
    for part in (sim, fem):
        source = executor.workspace.resolve(part.FullPath)
        shutil.copy2(source, folder / (source.name + ".before-material"))
    others = {p.FullPath: bool(p.IsModified) for p in s.Parts if p not in (sim, fem)}
    material, readback, mark = create_orthotropic(
        s,
        executor.nxopen,
        fem,
        conductivities=[12, 7, 0.4],
        density=1900,
        heat_capacity=900,
        name="ORTHOTROPIC_STUDY_12_7_04",
        provenance="Synthetic directional-conduction benchmark; not product material data",
    )
    collectors = fem.BaseFEModel.MeshManager.GetMeshCollectors()
    if len(collectors) != 1 or collectors[0].CollectorNeutralType != "Solid":
        raise ValueError("Requires exactly one solid collector")
    table = (
        collectors[0]
        .ElementPropertyTable.GetNamedPropertyTablePropertyValue("Solid Property")
        .PropertyTable
    )
    options = fem.NewMaterialOptions()
    try:
        options.Material, options.MaterialInherited = material, False
        table.SetPhysicalMaterialPropertyValue("material", options)
    finally:
        options.Dispose()
    actual = table.GetPhysicalMaterialPropertyValue("material")
    try:
        assert actual.Material == material and not actual.MaterialInherited
    finally:
        actual.Dispose()
    csys = table.GetCoordinateSystemPropertyValue("material orientation")
    orientation = {
        "type": table.GetIntegerPropertyValue("material orientation type"),
        "csys_present": csys is not None,
        "global_frame_interpretation": "not_verified",
    }
    fem_saved = executor._sim_save(executor._reference(fem, "part", fem, "part")["id"])
    sim_id = executor._reference(sim, "part", sim, "part")["id"]
    executor._sim_activate(sim_id)
    copied = executor._sim_save_as(
        sim_id, "ui-benchmarks/orthotropic-export-20260908-r1/orthotropic_export_r1.sim"
    )
    result = executor._sim_export_input(copied["document"]["id"])
    export_folder = executor.workspace.resolve(s.Parts.BaseWork.FullPath).parent
    decks = list(export_folder.glob("*.xml"))
    assert len(decks) == 1
    root = ET.parse(decks[0]).getroot()
    sections = {
        key: ET.tostring(root.find(key), encoding="unicode")
        for key in ("MaterialList", "PhysicalPropertyTableList")
        if root.find(key) is not None
    }
    assert all(
        {p.FullPath: bool(p.IsModified) for p in s.Parts}.get(path) == flag
        for path, flag in others.items()
    )
    receipt = {
        "state": "exported",
        "readback": readback,
        "orientation": orientation,
        "fem_saved": fem_saved,
        "copied": copied,
        "export": result,
        "material_sections": sections,
        "solver_launched": False,
    }
    (folder / "orthotropic-assignment-result.json").write_text(json.dumps(receipt, indent=2))
    return receipt

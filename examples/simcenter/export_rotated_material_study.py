"""Create an independent thermal study and inspect an explicit material frame."""


def run(executor):
    import xml.etree.ElementTree as ET

    from nx_mcp.simcenter.dependencies import inspect_direct
    from nx_mcp.simcenter.solver_guard import require_solver_idle
    from nx_mcp.simcenter.variant_clone import execute_clone_plan
    from nx_mcp.simcenter.variant_plan import plan_variant

    require_solver_idle()
    s, nx = executor.session, executor.nxopen
    source = s.Parts.BaseWork
    assert source.FullPath.endswith("orthotropic_solve_r1.sim")
    before = {p.FullPath: bool(p.IsModified) for p in s.Parts}
    plan = plan_variant(
        executor.workspace,
        inspect_direct(s, source, executor.workspace),
        folder="ui-benchmarks/orthotropic-rotated-20260908-r1",
        name="RotatedOrthoR1",
        saved_snapshot=True,
        loaded_paths=list(before),
    )
    clone = execute_clone_plan(s, executor.workspace, plan)
    opened = executor._sim_open(plan["mapping"][0]["destination"])
    sim = s.Parts.BaseWork
    fem = sim.FemPart
    executor._sim_activate(executor._reference(fem, "part", fem, "part")["id"])
    collectors = fem.BaseFEModel.MeshManager.GetMeshCollectors()
    assert len(collectors) == 1 and collectors[0].CollectorNeutralType == "Solid"
    table = (
        collectors[0]
        .ElementPropertyTable.GetNamedPropertyTablePropertyValue("Solid Property")
        .PropertyTable
    )
    assert table.GetCoordinateSystemPropertyValue("material orientation") is None
    orientation_type = table.GetIntegerPropertyValue("material orientation type")
    mark = s.SetUndoMark(nx.Session.MarkVisibility.Visible, "Isolated material axis swap")
    try:
        frame = fem.CoordinateSystems.CreateCoordinateSystem(
            nx.Point3d(0.0, 0.0, 0.0), nx.Vector3d(0.0, 1.0, 0.0), nx.Vector3d(-1.0, 0.0, 0.0)
        )
        frame.SetName("MCP_MATERIAL_X_TO_GLOBAL_Y")
        table.SetCoordinateSystemPropertyValue("material orientation", frame)
        assert table.GetCoordinateSystemPropertyValue("material orientation") == frame
        assert table.GetIntegerPropertyValue("material orientation type") == orientation_type
        matrix = frame.Orientation.Element
        readback = {
            "orientation_type": orientation_type,
            "matrix_fields": {
                key: getattr(matrix, key)
                for key in ("Xx", "Xy", "Xz", "Yx", "Yy", "Yz", "Zx", "Zy", "Zz")
            },
            "requested_material_x_in_part": [0, 1, 0],
            "requested_material_y_in_part": [-1, 0, 0],
        }
    except Exception:
        s.UndoToMark(mark, None)
        s.DeleteUndoMark(mark, None)
        raise
    saved = executor._sim_save(executor._reference(fem, "part", fem, "part")["id"])
    executor._sim_activate(opened["document"]["id"])
    copied = executor._sim_save_as(
        opened["document"]["id"],
        "ui-benchmarks/orthotropic-rotated-export-20260908-r1/rotated_ortho_export_r1.sim",
    )
    exported = executor._sim_export_input(copied["document"]["id"])
    root = ET.parse(exported["input_path"]).getroot()
    sections = {
        c.tag: ET.tostring(c, encoding="unicode")
        for c in root
        if c.tag in ("PhysicalPropertyTableList", "MaterialList")
        or "coord" in c.tag.lower()
        or "orient" in c.tag.lower()
    }
    after = {p.FullPath: bool(p.IsModified) for p in s.Parts}
    assert all(after.get(path) == flag for path, flag in before.items())
    return {
        "clone": clone,
        "frame_readback": readback,
        "saved": saved,
        "export": exported,
        "sections": sections,
        "source_flags_preserved": True,
        "solver_launched": False,
    }

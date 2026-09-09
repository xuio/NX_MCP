def run(executor):
    import time

    import NXOpen.CAE as cae

    from nx_mcp.simcenter.mesh_plan import mesh_counts
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    nx, session = executor.nxopen, executor.session
    fem = session.Parts.BaseWork
    assert isinstance(fem, cae.FemPart) and "L-face-size-20260909-r1" in fem.FullPath
    flags = [(p.FullPath, bool(p.IsModified)) for p in session.Parts]
    controls = fem.BaseFEModel.MeshControls
    manager = fem.BaseFEModel.MeshManager
    originals = list(controls)
    assert len(originals) == 1
    original_tags = [int(c.Tag) for c in originals]
    before = mesh_counts(fem)
    meshes = list(manager.GetMeshes())
    assert len(meshes) == 2
    mark = session.SetUndoMark(
        nx.Session.MarkVisibility.Visible, "NX MCP bounded face-size edit/remesh probe"
    )
    result = {
        "document": fem.FullPath,
        "before": before,
        "hypothesis": "Existing face density builder edits OverallSize; existing tetra builder CommitMesh regenerates with edited local sizing",
        "solver_launched": False,
    }
    start = time.monotonic()
    try:
        builder = controls.CreateBuilder(originals[0])
        try:
            assert builder.MainType == cae.MeshControlBuilder.Types.FaceDensitySize
            value = builder.OverallSize.GetValueUsingUnits(nx.Expression.UnitsOption.Expression)
            assert value == 1 and builder.OverallSize.Units.Name == "MilliMeter"
            faces = [int(f.Tag) for f in builder.Selection.GetArray()]
            builder.OverallSize.RightHandSide = "2.0"
            result["edit_returned_controls"] = len(list(builder.CommitDensities()))
        finally:
            builder.Destroy()
        current = list(controls)
        assert len(current) == 1
        reader = controls.CreateBuilder(current[0])
        try:
            result["size_mm"] = reader.OverallSize.GetValueUsingUnits(
                nx.Expression.UnitsOption.Expression
            )
            result["selection_preserved"] = faces == [
                int(f.Tag) for f in reader.Selection.GetArray()
            ]
            assert result["size_mm"] == 2 and result["selection_preserved"]
        finally:
            reader.Destroy()
        result["controls_before"] = original_tags
        result["controls_after"] = [int(c.Tag) for c in current]
        result["mesh_before_regeneration"] = mesh_counts(fem)
        result["regenerated"] = []
        for mesh in meshes:
            builder = manager.CreateMesh3dTetBuilder(mesh)
            try:
                size, unit = builder.PropertyTable.GetBaseScalarWithDataPropertyValue(
                    "quad mesh overall edge size"
                )
                assert size == 5 and unit.Name == "MilliMeter"
                assert builder.ElementType.ElementTypeName == "Linear Tetrahedron"
                result["regenerated"].append(len(list(builder.CommitMesh())))
            finally:
                builder.Destroy()
        result["after"] = mesh_counts(fem)
        assert result["after"]["elements"] < before["elements"]
        assert len(list(manager.GetMeshes())) == 2
        result["passed"] = True
    except Exception as error:
        result["passed"] = False
        result["error"] = {
            "type": type(error).__name__,
            "message": str(error),
            "nx_code": getattr(error, "ErrorCode", None),
        }
    finally:
        session.UndoToMark(mark, None)
        session.DeleteUndoMark(mark, None)
    result["elapsed_seconds"] = time.monotonic() - start
    result["mesh_restored"] = before == mesh_counts(fem)
    result["controls_restored"] = original_tags == [int(c.Tag) for c in controls]
    result["flags_restored"] = flags == [(p.FullPath, bool(p.IsModified)) for p in session.Parts]
    reader = controls.CreateBuilder(list(controls)[0])
    try:
        result["restored_size_mm"] = reader.OverallSize.GetValueUsingUnits(
            nx.Expression.UnitsOption.Expression
        )
    finally:
        reader.Destroy()
    fem.ModelingViews.WorkView.Fit()
    fem.ModelingViews.WorkView.UpdateDisplay()
    return result

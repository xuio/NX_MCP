def run(executor):
    import NXOpen.CAE as cae
    import NXOpen.UF as uf

    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    nx, session = executor.nxopen, executor.session
    fem = session.Parts.BaseWork
    assert isinstance(fem, cae.FemPart) and "M-mixed-mesh-20260909-r1" in fem.FullPath
    collection = fem.BaseFEModel.MeshControls
    before = {int(c.Tag) for c in collection}
    flags = [(p.FullPath, bool(p.IsModified)) for p in session.Parts]
    body = list(fem.Bodies)[0]
    _, tags = uf.UFSession.GetUFSession().Sf.BodyAskFaces(body.Tag)
    face = nx.TaggedObjectManager.GetTaggedObject(tags[0])
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "NX MCP local face-size probe")
    result = {
        "hypothesis": "FaceDensitySize uses OverallSize and Selection; no mesh regeneration",
        "document": fem.FullPath,
    }
    try:
        builder = collection.CreateBuilder(None)
        try:
            result["enum_available"] = hasattr(cae.MeshControlBuilder.Types, "FaceDensitySize")
            builder.MainType = cae.MeshControlBuilder.Types.FaceDensitySize
            result["size_units_before"] = builder.OverallSize.Units.Name
            assert builder.OverallSize.Units.Name == "MilliMeter"
            builder.OverallSize.RightHandSide = "1.0"
            builder.Selection.Add([face])
            controls = list(builder.CommitDensities())
        finally:
            builder.Destroy()
        result["created_count"] = len(controls)
        result["controls"] = []
        for control in controls:
            reader = collection.CreateBuilder(control)
            try:
                result["controls"].append(
                    {
                        "type": str(reader.MainType),
                        "size": reader.OverallSize.GetValueUsingUnits(
                            nx.Expression.UnitsOption.Expression
                        ),
                        "units": reader.OverallSize.Units.Name,
                        "face_tags": [int(f.Tag) for f in reader.Selection.GetArray()],
                        "expected_face": int(face.Tag),
                    }
                )
            finally:
                reader.Destroy()
    except Exception as error:
        result["error"] = {"message": str(error), "nx_code": getattr(error, "ErrorCode", None)}
    finally:
        session.UndoToMark(mark, None)
        session.DeleteUndoMark(mark, None)
    result["inventory_restored"] = before == {int(c.Tag) for c in collection}
    result["flags_restored"] = flags == [(p.FullPath, bool(p.IsModified)) for p in session.Parts]
    return result

def run(executor):
    import NXOpen.CAE as cae
    from nx_mcp.simcenter.solver_guard import require_solver_idle
    from nx_mcp.simcenter.mesh_plan import mesh_counts

    require_solver_idle()
    nx, session = executor.nxopen, executor.session
    fem = session.Parts.BaseWork
    if not isinstance(fem, cae.FemPart) or "public-multibody-analysis-r1" not in fem.FullPath:
        raise ValueError("Expected isolated multi-body FEM")
    cad = fem.MasterCadPart
    if len(list(cad.Bodies)) != 17 or len(list(fem.Bodies)) != 17:
        raise ValueError("Expected initial 17-body fixture")
    rows = []

    def read(stage):
        rows.append(
            {
                "stage": stage,
                "cad_bodies": len(list(cad.Bodies)),
                "fem_bodies": len(list(fem.Bodies)),
                "mesh_counts": mesh_counts(fem),
            }
        )

    read("before")
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "NX MCP isolated topology probe")
    try:
        fem.SetAssociatedCadAsWork(cad)
        builder = cad.Features.CreateBlockFeatureBuilder(None)
        try:
            builder.SetOriginAndLengths(nx.Point3d(90.0, 0.0, 0.0), "3", "3", "3")
            feature = builder.CommitFeature()
        finally:
            builder.Destroy()
        fem.SetFemAsWork()
        data = fem.GetGeometryDataWithAttributes()
        try:
            fem.SetGeometryDataWithAttributes(
                cae.FemPart.UseBodiesOption.AllBodies, [], data[2], data[3]
            )
            fem.BaseFEModel.UpdateFemodel()
        finally:
            data[2].Dispose()
        read("added")
        assert len(list(fem.Bodies)) == 18
        fem.SetAssociatedCadAsWork(cad)
        session.UpdateManager.AddToDeleteList(feature)
        if session.UpdateManager.DoUpdate(mark):
            raise ValueError("Native delete update returned errors")
        fem.SetFemAsWork()
        fem.BaseFEModel.UpdateFemodel()
        read("removed")
        assert len(list(fem.Bodies)) == 17
        from nx_mcp.simcenter.postviews import present_result

        presentation = present_result(session, fem)
        return {
            "rows": rows,
            "passed": True,
            "saved": False,
            "solver_launched": False,
            "presentation": presentation,
        }
    except Exception as error:
        import traceback

        detail = traceback.format_exc()
        session.UndoToMark(mark, None)
        return {
            "passed": False,
            "error": str(error),
            "traceback": detail,
            "rows": rows,
            "after_undo": {
                "cad_bodies": len(list(cad.Bodies)),
                "fem_bodies": len(list(fem.Bodies)),
            },
        }
    finally:
        for part in list(session.Parts):
            if (
                part == cad
                or part == fem
                or (isinstance(part, cae.SimPart) and part.FemPart == fem)
            ):
                executor.objects.invalidate_part(executor._part_id(part))

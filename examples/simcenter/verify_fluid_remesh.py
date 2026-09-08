def run(executor):
    import NXOpen as nx

    s = executor.session
    sim = s.Parts.BaseWork
    if type(sim).__name__ != "SimPart" or "D-cavity-documents-20260908-r2" not in sim.FullPath:
        raise ValueError("Isolated cavity SIM required")
    fem = sim.FemPart
    manager = fem.BaseFEModel.MeshManager
    meshes = list(manager.GetMeshes())
    if len(meshes) != 1:
        raise ValueError("Expected exactly one existing mesh")

    def counts():
        e = fem.BaseFEModel.FeelementLabelMap
        n = fem.BaseFEModel.FenodeLabelMap
        try:
            return {"elements": e.NumElements, "nodes": n.NumNodes}
        finally:
            e.Dispose()
            n.Dispose()

    before = counts()
    display = s.Parts.BaseDisplay
    _, st = s.Parts.SetDisplay(fem, False, False)
    if st:
        st.Dispose()
    s.Parts.SetWork(fem)
    mark = s.SetUndoMark(nx.Session.MarkVisibility.Visible, "Inspect fluid mesh refinement")
    builder = None
    try:
        builder = manager.CreateMesh3dTetBuilder(meshes[0])
        old_size, unit = builder.PropertyTable.GetBaseScalarWithDataPropertyValue(
            "quad mesh overall edge size"
        )
        old_type = builder.ElementType.ElementTypeName
        if old_size != 5.0 or old_type != "Fluid Linear Tetrahedron":
            raise ValueError("Unexpected existing mesh parameters")
        builder.AutoSizeOption = False
        builder.PropertyTable.SetBaseScalarWithDataPropertyValue(
            "quad mesh overall edge size", 3.0, unit
        )
        created = list(builder.CommitMesh())
        builder.Destroy()
        builder = None
        current = list(manager.GetMeshes())
        if len(current) != 1:
            raise ValueError("Refinement changed mesh count")
        reader = manager.CreateMesh3dTetBuilder(current[0])
        try:
            value, u = reader.PropertyTable.GetBaseScalarWithDataPropertyValue(
                "quad mesh overall edge size"
            )
            if value != 3.0 or reader.ElementType.ElementTypeName != old_type:
                raise ValueError("Refined mesh readback differs")
        finally:
            reader.Destroy()
        after = counts()
        if after["elements"] <= before["elements"]:
            raise ValueError("Element count did not increase")
        fem.ModelingViews.WorkView.Fit()
        return {
            "before": before,
            "refined": after,
            "before_size_mm": old_size,
            "after_size_mm": value,
            "native_type": old_type,
            "commit_mesh_count": len(created),
            "disposable_probe": True,
            "saved": False,
        }
    finally:
        if builder:
            builder.Destroy()
        try:
            s.UndoToMark(mark, None)
            s.DeleteUndoMark(mark, None)
            if counts() != before:
                raise RuntimeError("Mesh counts differ after rollback")
        finally:
            _, st = s.Parts.SetDisplay(display, False, False)
            if st:
                st.Dispose()
            s.Parts.SetWork(sim)

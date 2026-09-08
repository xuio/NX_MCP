def run(executor):
    import importlib

    import NXOpen.CAE as cae

    import nx_mcp.simcenter.properties as props

    importlib.reload(props)
    s = executor.session
    fem = next(
        p
        for p in s.Parts
        if isinstance(p, cae.FemPart) and "D-cavity-documents-20260908-r2" in p.FullPath
    )
    oldwork, olddisplay = s.Parts.BaseWork, s.Parts.BaseDisplay
    _, st = s.Parts.SetDisplay(fem, False, False)
    if st:
        st.Dispose()
    s.Parts.SetWork(fem)
    mark = s.SetUndoMark(
        executor.nxopen.Session.MarkVisibility.Visible, "Inspect fluid material properties"
    )
    builder = None
    try:
        collector = fem.BaseFEModel.MeshManager.GetMeshCollectors()[0]
        table = collector.ElementPropertyTable.GetNamedPropertyTablePropertyValue("Fluid Property")
        assigned = props.read_properties(table.PropertyTable, executor.nxopen)
        builder = fem.MaterialManager.PhysicalMaterials.CreatePhysicalMaterialBuilder(
            executor.nxopen.PhysicalMaterial.Type.Fluid
        )
        return {
            "current_assignment": assigned,
            "fluid_material_properties": props.read_properties(
                builder.PropertyTable, executor.nxopen
            ),
        }
    finally:
        if builder is not None:
            builder.Destroy()
        s.UndoToMark(mark, None)
        s.DeleteUndoMark(mark, None)
        _, st = s.Parts.SetDisplay(olddisplay, False, False)
        if st:
            st.Dispose()
        s.Parts.SetWork(oldwork)

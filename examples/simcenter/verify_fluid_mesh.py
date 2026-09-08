"""Native-thread fixture: coarse fluid mesh in the isolated cavity FEM only."""


def run(executor):
    import json
    from pathlib import Path

    from nx_mcp.simcenter.fluid_domain import inspect_region_geometry
    from nx_mcp.simcenter.properties import read_properties

    session = executor.session
    fem = session.Parts.BaseWork
    if "D-cavity-documents-20260908-r2" not in fem.FullPath:
        raise ValueError("Requires isolated cavity FEM")
    receipt = Path(fem.FullPath).parent / "fluid-mesh-01.json"
    if receipt.exists():
        return {"replayed": True, "receipt": json.loads(receipt.read_text())}
    manager = fem.BaseFEModel.MeshManager
    if manager.GetMeshes():
        raise ValueError("Existing mesh: inspect before attempting another run")
    recipes = list(fem.BaseFEModel.FluidDomains)
    if len(recipes) != 1:
        raise ValueError("Expected one cavity region")
    bodies = list(recipes[0].GetFluidBodies())
    geometry = inspect_region_geometry(fem, bodies)
    if len(bodies) != 1 or abs(geometry["bodies"][0]["volume_mm3"] - 64000) > 0.01:
        raise ValueError("Cavity volume differs from benchmark")
    mark = session.SetUndoMark(
        executor.nxopen.Session.MarkVisibility.Visible, "MCP fluid mesh benchmark"
    )
    builder = None
    try:
        builder = manager.CreateMesh3dTetBuilder(None)
        element_type = "Fluid Linear Tetrahedron"
        if element_type not in builder.ElementType.GetElementTypeNames():
            raise ValueError("Native solver does not offer the required fluid element")
        builder.ElementType.ElementTypeName = element_type
        builder.ElementType.DestinationCollector.AutomaticMode = True
        builder.AutoSizeOption = False
        builder.PropertyTable.SetBaseScalarWithDataPropertyValue(
            "quad mesh overall edge size", 5.0, fem.UnitCollection.FindObject("MilliMeter")
        )
        builder.SelectionList.Add(bodies)
        meshes = list(builder.CommitMesh())
        builder.Destroy()
        builder = None
        if not meshes:
            raise ValueError("No native mesh generated")
        actual = []
        for mesh in meshes:
            reader = manager.CreateMesh3dTetBuilder(mesh)
            try:
                if reader.ElementType.ElementTypeName != element_type:
                    raise ValueError("Committed element type differs")
                actual.append(
                    {
                        "name": mesh.Name,
                        "type": type(mesh).__name__,
                        "element_type": reader.ElementType.ElementTypeName,
                        "properties": read_properties(reader.PropertyTable, executor.nxopen),
                    }
                )
            finally:
                reader.Destroy()
        elements = fem.BaseFEModel.FeelementLabelMap
        nodes = fem.BaseFEModel.FenodeLabelMap
        try:
            counts = {"elements": elements.NumElements, "nodes": nodes.NumNodes}
        finally:
            elements.Dispose()
            nodes.Dispose()
        if counts["elements"] <= 0 or counts["nodes"] <= 0:
            raise ValueError("Native mesh has no elements or nodes")
        result = {
            "geometry": geometry,
            "meshes": actual,
            "counts": counts,
            "requested_size_mm": 5.0,
            "quality_validation": "not_performed",
            "solve_launched": False,
            "saved": False,
        }
        fem.ModelingViews.WorkView.Fit()
        with receipt.open("x") as stream:
            json.dump(result, stream, indent=2)
        return result
    except Exception as error:
        if builder is not None:
            builder.Destroy()
            builder = None
        session.UndoToMark(mark, None)
        if manager.GetMeshes():
            raise RuntimeError("Mesh rollback incomplete") from error
        session.DeleteUndoMark(mark, None)
        raise
    finally:
        if builder is not None:
            builder.Destroy()

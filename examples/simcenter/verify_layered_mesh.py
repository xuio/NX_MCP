"""Verify native wall-targeted boundary-layer control and undo without remeshing."""


def run(executor):
    import importlib

    import NXOpen.UF as uf

    from nx_mcp.simcenter import boundary_layers

    importlib.reload(boundary_layers)
    s = executor.session
    sim = s.Parts.BaseWork
    if type(sim).__name__ != "SimPart" or "D-cavity-documents-20260908-r2" not in sim.FullPath:
        raise ValueError("Isolated cavity required")
    fem = sim.FemPart
    sf = uf.UFSession.GetUFSession().Sf
    bodies = list(list(fem.BaseFEModel.FluidDomains)[0].GetFluidBodies())
    if len(bodies) != 1:
        raise ValueError("Expected one fluid body")
    _, tags = sf.BodyAskFaces(bodies[0].Tag)
    walls = []
    for tag in tags:
        box = list(sf.FaceAskBoundingBox(tag))
        if abs(box[3] - box[0] - 160.0) < 1e-6:
            walls.append(executor.nxopen.TaggedObjectManager.GetTaggedObject(tag))
    if len(walls) != 4:
        raise ValueError("Expected four walls")
    _, st = s.Parts.SetDisplay(fem, False, False)
    if st:
        st.Dispose()
    s.Parts.SetWork(fem)
    em = fem.BaseFEModel.FeelementLabelMap
    try:
        before_elements = em.NumElements
    finally:
        em.Dispose()
    before = {int(c.Tag) for c in fem.BaseFEModel.MeshControls}
    mark = s.SetUndoMark(executor.nxopen.Session.MarkVisibility.Visible, "Verify layer adapter")
    try:
        result = boundary_layers.create_boundary_layers(
            s, fem, walls, first_layer_mm=0.1, layers=8, growth_rate=1.2
        )
        result.pop("control")
        manager = fem.BaseFEModel.MeshManager
        meshes = list(manager.GetMeshes())
        if len(meshes) != 1:
            raise ValueError("Expected one existing fluid mesh")
        builder = manager.CreateMesh3dTetBuilder(meshes[0])
        try:
            generated = list(builder.CommitMesh())
        finally:
            builder.Destroy()
        em, nm = fem.BaseFEModel.FeelementLabelMap, fem.BaseFEModel.FenodeLabelMap
        try:
            result["mesh_counts"] = {"elements": em.NumElements, "nodes": nm.NumNodes}
        finally:
            em.Dispose()
            nm.Dispose()
        result["generated_mesh_count"] = len(generated)
        result["meshes"] = [{"name": m.Name, "type": type(m).__name__} for m in manager.GetMeshes()]
        checker = fem.ModelCheckMgr.CreateElementQualityCheckBuilder()
        checks = None
        try:
            checker.SelectionList.Add(list(manager.GetMeshes()))
            checks = checker.ExecuteCheck()
            result["quality"] = {
                "element_count": checks.ElementTestCount,
                "tests": [
                    {
                        "type": str(t.TestType),
                        "count": t.TestCount,
                        "errors": t.ErrorCount,
                        "warnings": t.WarnedCount,
                        "worst_value": t.WorstTestValue if t.HasTestValue else None,
                    }
                    for t in checks.GetTestSummary()
                ],
            }
        finally:
            if checks is not None:
                checks.Dispose()
            checker.Destroy()
        from nx_mcp.simcenter.properties import read_properties

        assignments = []
        for collector in manager.GetMeshCollectors():
            table = collector.ElementPropertyTable.GetNamedPropertyTablePropertyValue(
                "Fluid Property"
            )
            if table is None:
                raise ValueError("Generated collector lacks Fluid Property")
            inherited, material = table.PropertyTable.GetMaterialPropertyValue("material")
            if material is None:
                raise ValueError("Generated collector has no explicit material readback")
            assignments.append(
                {
                    "collector": collector.Name,
                    "material": material.Name,
                    "inherited": inherited,
                    "properties": [
                        p
                        for p in read_properties(material.GetPropTable(), executor.nxopen)
                        if p["name"]
                        in ("MassDensity", "DynamicVisc", "ThermalConductivity", "SpecificHeat")
                    ],
                }
            )
        result["material_assignments"] = assignments
        element_map = fem.BaseFEModel.FeelementLabelMap
        by_node_count = {}
        try:
            label = 0
            for _ in range(element_map.NumElements):
                label = element_map.AskNextElementLabel(label)
                element = element_map.GetElement(label)
                count = len(element.GetNodes())
                by_node_count[str(count)] = by_node_count.get(str(count), 0) + 1
        finally:
            element_map.Dispose()
        result["element_node_cardinalities"] = by_node_count
        result["mesh_generated"] = True
        result["disposable_probe"] = True
        result["mesh_regeneration_required"] = False
        return result
    finally:
        s.UndoToMark(mark, None)
        s.DeleteUndoMark(mark, None)
        if before != {int(c.Tag) for c in fem.BaseFEModel.MeshControls}:
            raise RuntimeError("Layer control rollback differs")
        em = fem.BaseFEModel.FeelementLabelMap
        try:
            if em.NumElements != before_elements:
                raise RuntimeError("Mesh did not restore after layered probe")
        finally:
            em.Dispose()
        _, st = s.Parts.SetDisplay(sim, False, False)
        if st:
            st.Dispose()
        s.Parts.SetWork(sim)

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
    before = {int(c.Tag) for c in fem.BaseFEModel.MeshControls}
    mark = s.SetUndoMark(executor.nxopen.Session.MarkVisibility.Visible, "Verify layer adapter")
    try:
        result = boundary_layers.create_boundary_layers(
            s, fem, walls, first_layer_mm=0.1, layers=8, growth_rate=1.2
        )
        result.pop("control")
        return result
    finally:
        s.UndoToMark(mark, None)
        s.DeleteUndoMark(mark, None)
        if before != {int(c.Tag) for c in fem.BaseFEModel.MeshControls}:
            raise RuntimeError("Layer control rollback differs")
        _, st = s.Parts.SetDisplay(sim, False, False)
        if st:
            st.Dispose()
        s.Parts.SetWork(sim)

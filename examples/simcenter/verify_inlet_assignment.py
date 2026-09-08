"""Isolated native inlet authoring test; default mode semantics remain unverified."""


def run(executor):
    import json
    from pathlib import Path

    import NXOpen.CAE as cae
    import NXOpen.UF as uf_module

    from nx_mcp.simcenter.boundaries import verify_face_targets
    from nx_mcp.simcenter.properties import read_properties

    s = executor.session
    sim = next(
        p for p in s.Parts if isinstance(p, cae.SimPart) and "D-flow-mcp-20260908" in p.FullPath
    )
    receipt = Path(sim.FullPath).parent / "inlet-assignment-01.json"
    if receipt.exists():
        return {"replayed": True, "receipt": json.loads(receipt.read_text())}
    if list(sim.Simulation.SimulationObjects):
        raise ValueError("Expected no existing boundaries")
    fem = sim.FemPart
    sf = uf_module.UFSession.GetUFSession().Sf
    candidates = []
    for body in fem.Bodies:
        _, tags = sf.BodyAskFaces(body.Tag)
        for tag in tags:
            box = list(sf.FaceAskBoundingBox(tag))
            if abs(box[0]) < 1e-7 and abs(box[3]) < 1e-7:
                candidates.append(executor.nxopen.TaggedObjectManager.GetTaggedObject(tag))
    if len(candidates) != 1:
        raise ValueError("Expected one inlet plane at x=0")
    component = sim.ComponentAssembly.RootComponent.GetChildren()[0]
    face = component.FindOccurrence(candidates[0])
    _, st = s.Parts.SetDisplay(sim, False, False)
    if st:
        st.Dispose()
    s.Parts.SetWork(sim)
    mark = s.SetUndoMark(
        executor.nxopen.Session.MarkVisibility.Visible, "MCP inlet authoring fixture"
    )
    builder = None
    try:
        builder = sim.Simulation.CreateBcBuilderForSimulationObjectDescriptor(
            "Inlet", "MCP Inlet authoring test"
        )
        expression = sim.Expressions.CreateSystemNumberExpression(
            "1.0", sim.UnitCollection.FindObject("MeterPerSecond")
        )
        wrapper = sim.FieldManager.CreateScalarFieldWrapperWithExpression(expression)
        builder.PropertyTable.SetScalarFieldWrapperPropertyValue("Velocity", wrapper)
        member = cae.SetObject()
        member.Obj = face
        member.SubType = cae.CaeSetObjectSubType.NotSet
        member.SubId = 0
        builder.TargetSetManager.SetTargetSetMembers(0, [member])
        boundary = builder.CommitAddBc()
        builder.Destroy()
        builder = None
        targets = verify_face_targets(boundary, [face])
        props = read_properties(boundary.PropertyTable, executor.nxopen)
        value = next(p for p in props if p["name"] == "Velocity")
        if float(value["expression"]) != 1.0 or value["units"] != "MeterPerSecond":
            raise ValueError("Velocity readback mismatch")
        result = {
            "name": boundary.Name,
            "type": type(boundary).__name__,
            "properties": props,
            "targets": targets,
            "solver_semantics": "not_verified",
            "solve_launched": False,
            "saved": False,
        }
        with receipt.open("x") as f:
            json.dump(result, f, indent=2)
        return result
    except Exception:
        if builder is not None:
            builder.Destroy()
            builder = None
        s.UndoToMark(mark, None)
        if list(sim.Simulation.SimulationObjects):
            raise RuntimeError("Inlet rollback incomplete") from None
        s.DeleteUndoMark(mark, None)
        raise
    finally:
        if builder is not None:
            builder.Destroy()

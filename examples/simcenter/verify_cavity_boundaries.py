"""Native cavity boundary authoring; export must still verify mode conventions."""


def run(executor):
    import json
    from pathlib import Path

    import NXOpen.CAE as cae
    import NXOpen.UF as uf

    from nx_mcp.simcenter.boundaries import verify_face_targets
    from nx_mcp.simcenter.properties import read_properties

    s, nx = executor.session, executor.nxopen
    sim = s.Parts.BaseWork
    if type(sim).__name__ != "SimPart" or "D-cavity-documents-20260908-r2" not in sim.FullPath:
        raise ValueError("Cavity SIM required")
    record = Path(sim.FullPath).parent / "cavity-boundaries-01.json"
    if record.exists():
        return {"replayed": True, "receipt": json.loads(record.read_text())}
    if list(sim.Simulation.SimulationObjects):
        raise ValueError("Inspect existing boundaries before retry")
    fem = sim.FemPart
    sf = uf.UFSession.GetUFSession().Sf
    bodies = list(list(fem.BaseFEModel.FluidDomains)[0].GetFluidBodies())
    if len(bodies) != 1:
        raise ValueError("Expected one fluid body")
    _, tags = sf.BodyAskFaces(bodies[0].Tag)
    component = sim.ComponentAssembly.RootComponent.GetChildren()[0]
    specs = [
        ("Inlet", 1.0, {"Velocity": (1.0, "MeterPerSecond")}),
        (
            "Opening",
            161.0,
            {
                "Pressure Value": (101325.0, "PressurePascals"),
                "External Relative Pressure": (0.0, "PressurePascals"),
            },
        ),
    ]
    targets = []
    for _descriptor, x, _values in specs:
        selected = [
            t for t in tags if all(abs(sf.FaceAskBoundingBox(t)[i] - x) < 1e-7 for i in [0, 3])
        ]
        if len(selected) != 1:
            raise ValueError("Ambiguous cavity end face")
        targets.append(
            component.FindOccurrence(nx.TaggedObjectManager.GetTaggedObject(selected[0]))
        )
    mark = s.SetUndoMark(nx.Session.MarkVisibility.Visible, "MCP cavity boundaries")
    builder = None
    try:
        out = []
        for (descriptor, x, values), face in zip(specs, targets, strict=True):
            builder = sim.Simulation.CreateBcBuilderForSimulationObjectDescriptor(
                descriptor, "Duct " + descriptor
            )
            for key, (value, unit) in values.items():
                expr = sim.Expressions.CreateSystemNumberExpression(
                    str(value), sim.UnitCollection.FindObject(unit)
                )
                wrapper = sim.FieldManager.CreateScalarFieldWrapperWithExpression(expr)
                builder.PropertyTable.SetScalarFieldWrapperPropertyValue(key, wrapper)
            member = cae.SetObject()
            member.Obj = face
            member.SubType = cae.CaeSetObjectSubType.NotSet
            member.SubId = 0
            builder.TargetSetManager.SetTargetSetMembers(0, [member])
            boundary = builder.CommitAddBc()
            builder.Destroy()
            builder = None
            props = read_properties(boundary.PropertyTable, nx)
            for key, (value, unit) in values.items():
                actual = next(p for p in props if p["name"] == key)
                if float(actual["expression"]) != value or actual["units"] != unit:
                    raise ValueError(f"Boundary value readback mismatch: {descriptor} {key}: {actual!r}")
            out.append(
                {
                    "descriptor": descriptor,
                    "name": boundary.Name,
                    "plane_x_mm": x,
                    "targets": verify_face_targets(boundary, [face]),
                    "properties": props,
                }
            )
        result = {
            "boundaries": out,
            "mode_conventions": "native defaults; solver input validation pending",
            "solve_launched": False,
            "saved": False,
        }
        with record.open("x") as f:
            json.dump(result, f, indent=2)
        return result
    except Exception:
        if builder is not None:
            builder.Destroy()
            builder = None
        s.UndoToMark(mark, None)
        if list(sim.Simulation.SimulationObjects):
            raise RuntimeError("Boundary rollback incomplete") from None
        s.DeleteUndoMark(mark, None)
        raise
    finally:
        if builder is not None:
            builder.Destroy()

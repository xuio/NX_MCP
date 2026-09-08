"""Batch generic coupled boundary authoring with selections and property readback."""


def run(executor, *, variant="baseline"):
    import json
    import time

    import NXOpen as nx
    import NXOpen.CAE as cae
    import NXOpen.UF as uf

    from nx_mcp.simcenter.boundaries import verify_face_targets
    from nx_mcp.simcenter.heat_loads import create_body_power
    from nx_mcp.simcenter.properties import read_properties
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    if variant not in (
        "baseline",
        "refined",
        "fine",
        "layer_coarse",
        "layer_fine",
        "stock_material",
        "stock_copy",
        "material_contrast",
    ):
        raise ValueError("Select a bounded finned fixture variant")
    sim = executor.session.Parts.BaseWork
    if f"E-finned-{variant}-20260908-r1" not in sim.FullPath:
        raise ValueError("Requires current coupled steady fixture")
    receipt = executor.workspace.resolve(
        f"ui-benchmarks/E-finned-{variant}-boundaries-20260908-r1.json"
    )
    if receipt.exists():
        return {"replayed": True, "receipt": json.loads(receipt.read_text())}
    if list(sim.Simulation.SimulationObjects) or list(sim.Simulation.Loads):
        raise ValueError("Inspect existing objects before any replay")
    started = time.monotonic()
    rows = []

    def record():
        receipt.write_text(json.dumps({"rows": rows, "solver_launched": False}, indent=2))

    rows.append({"stage": "intent"})
    record()
    fem = sim.FemPart
    rows.append(
        {
            "stage": "mesh_quality",
            "result": executor._sim_mesh_quality(
                executor._reference(fem, "part", fem, "FEM")["id"], True
            ),
        }
    )
    record()
    quality = rows[-1]["result"]
    if quality["error_occurrences"]:
        raise ValueError(
            "Native mesh quality errors; inspect retained receipt before boundary authoring or solve"
        )
    sf = uf.UFSession.GetUFSession().Sf
    bodies = sorted(fem.Bodies, key=lambda b: sf.BodyAskBoundingBox(b.Tag)[2])
    component = sim.ComponentAssembly.RootComponent.GetChildren()[0]
    solid = component.FindOccurrence(bodies[0])
    _, face_tags = sf.BodyAskFaces(bodies[1].Tag)
    for descriptor, x in [("Inlet", 0.0), ("Opening", 20.0)]:
        selected = [
            t
            for t in face_tags
            if abs(sf.FaceAskBoundingBox(t)[0] - x) < 1e-7
            and abs(sf.FaceAskBoundingBox(t)[3] - x) < 1e-7
        ]
        assert len(selected) == 1
        face = component.FindOccurrence(nx.TaggedObjectManager.GetTaggedObject(selected[0]))
        mark = executor.session.SetUndoMark(
            nx.Session.MarkVisibility.Visible, "MCP coupled " + descriptor
        )
        builder = None
        try:
            builder = sim.Simulation.CreateBcBuilderForSimulationObjectDescriptor(
                descriptor, "Coupled " + descriptor
            )
            if descriptor == "Inlet":
                expression = sim.Expressions.CreateSystemNumberExpression(
                    "1.0", sim.UnitCollection.FindObject("MeterPerSecond")
                )
                wrapper = sim.FieldManager.CreateScalarFieldWrapperWithExpression(expression)
                builder.PropertyTable.SetScalarFieldWrapperPropertyValue("Velocity", wrapper)
            else:
                builder.PropertyTable.SetIntegerPropertyValue("Pressure", 1)
                builder.PropertyTable.SetIntegerPropertyValue("External Pressure Type", 0)
                pressure = sim.Expressions.CreateSystemNumberExpression(
                    "101325.0", sim.UnitCollection.FindObject("PressurePascals")
                )
                builder.PropertyTable.SetScalarFieldWrapperPropertyValue(
                    "Pressure Value",
                    sim.FieldManager.CreateScalarFieldWrapperWithExpression(pressure),
                )
            member = cae.SetObject()
            member.Obj = face
            member.SubType = cae.CaeSetObjectSubType.NotSet
            member.SubId = 0
            builder.TargetSetManager.SetTargetSetMembers(0, [member])
            bc = builder.CommitAddBc()
            builder.Destroy()
            builder = None
            rows.append(
                {
                    "stage": descriptor,
                    "targets": verify_face_targets(bc, [face]),
                    "properties": read_properties(bc.PropertyTable, nx),
                }
            )
            record()
        except Exception as error:
            if builder:
                builder.Destroy()
            executor.session.UndoToMark(mark, None)
            rows.append(
                {
                    "stage": descriptor,
                    "error": type(error).__name__,
                    "nx_code": getattr(error, "ErrorCode", None),
                }
            )
            record()
            raise
    heat = create_body_power(
        executor.session, sim, solid, 0.1, "Generic solid 0.1 W", "Assumed constant benchmark heat"
    )
    heat.pop("load", None)
    rows.append({"stage": "heat", "result": heat})
    record()
    from nx_mcp.simcenter.external_conditions import assign_external_temperature

    boundaries = list(sim.Simulation.SimulationObjects)
    external = assign_external_temperature(
        executor.session, sim, boundaries, "Finned external air 20 C", 20.0
    )
    external["table"] = external["table"].Name
    rows.append({"stage": "external", "result": external})
    record()
    solution = sim.Simulation.ActiveSolution
    solution.ActiveStep.PropertyTable.SetIntegerPropertyValue("Solution Type", 0)
    assert solution.ActiveStep.PropertyTable.GetIntegerPropertyValue("Solution Type") == 0
    solution.PropertyTable.SetScalarWithDataPropertyValue(
        "Fluid Temperature", 0.0, sim.UnitCollection.FindObject("Celsius")
    )
    solution.PropertyTable.SetIntegerPropertyValue("Ambient Pressure", 1)
    solution.PropertyTable.SetIntegerPropertyValue("Turbulence Model", 0)
    surface = solution.PropertyTable.GetNamedPropertyTablePropertyValue(
        "Flow Surface Parameters"
    ).PropertyTable
    surface.SetIntegerPropertyValue("Wall Treatment", 0)
    for key, property_name in (
        ("Thermal Parameters", "Thermal Steady State - Iteration Limit"),
        ("Flow Solution Parameters", "3D Flow Steady State - Iteration Limit"),
    ):
        props = solution.PropertyTable.GetNamedPropertyTablePropertyValue(key).PropertyTable
        props.SetIntegerPropertyValue(property_name, 500)
        assert props.GetIntegerPropertyValue(property_name) == 500
    actual_members = {b.Name for b in solution.GetBcs()}
    assert actual_members == {"Coupled Inlet", "Coupled Opening", "Generic solid 0.1 W"}, (
        actual_members
    )
    assert not solution.ActiveStep.GetBcs()
    rows.append({"stage": "effective_membership", "solution": sorted(actual_members), "step": []})
    status = sim.Save(nx.BasePart.SaveComponents.FalseValue, nx.BasePart.CloseAfterSave.FalseValue)
    if status:
        status.Dispose()
    rows.append(
        {
            "stage": "solution_properties",
            "properties": read_properties(sim.Simulation.ActiveSolution.PropertyTable, nx),
            "elapsed_seconds": time.monotonic() - started,
        }
    )
    record()
    return {"rows": rows, "saved": True, "solver_launched": False, "interfaces_validated": False}

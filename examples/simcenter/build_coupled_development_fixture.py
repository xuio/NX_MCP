"""Small coupled solid/air authoring fixture. Checkpoints prevent blind replay."""


def run(executor):
    import json
    import time
    import NXOpen as nx
    import NXOpen.CAE as cae
    import NXOpen.UF as uf
    from nx_mcp.simcenter.flow import create_initial_step, attach_default_tables
    from nx_mcp.simcenter.fluid_material import assign_fluid_material
    from nx_mcp.simcenter.properties import read_properties
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    root = executor.workspace.resolve("ui-benchmarks/E-development-20260908-r1")
    receipt = executor.workspace.resolve("ui-benchmarks/E-development-20260908-r1.json")
    if receipt.exists():
        return {
            "replayed": True,
            "receipt": json.loads(receipt.read_text()),
            "automatic_resume": False,
        }
    data = {"stages": {}, "numerical_acceptance": False, "solver_launched": False}

    def record(stage, value):
        data["stages"][stage] = value
        receipt.write_text(json.dumps(data, indent=2))

    record("intent", {"folder": str(root)})
    started = time.monotonic()
    created = executor._sim_create_benchmark(
        str(root), 20.0, 10.0, 5.0, "coupled_thermal_flow", block_origins_mm=[[0, 0, 0], [0, 0, 5]]
    )
    record("create", {"result": created, "elapsed_seconds": time.monotonic() - started})
    sim = executor.session.Parts.BaseWork
    fem = next(
        p for p in executor.session.Parts if isinstance(p, cae.FemPart) and str(root) in p.FullPath
    )
    record("step", create_initial_step(executor.session, sim, "Coupled development"))
    record("tables", attach_default_tables(executor.session, sim, "Development"))
    _, status = executor.session.Parts.SetDisplay(fem, False, False)
    if status:
        status.Dispose()
    executor.session.Parts.SetWork(fem)
    sf = uf.UFSession.GetUFSession().Sf
    bodies = sorted(list(fem.Bodies), key=lambda b: sf.BodyAskBoundingBox(b.Tag)[2])
    assert len(bodies) == 2
    record(
        "geometry",
        [
            {
                "bounds_mm": list(sf.BodyAskBoundingBox(b.Tag)),
                "volume_mm3": sf.BodyAskVolumeAndCentroid(b.Tag)[0],
            }
            for b in bodies
        ],
    )
    manager = fem.BaseFEModel.MeshManager
    for body, role, element in zip(
        bodies, ("solid", "air"), ("Linear Tetrahedron", "Fluid Linear Tetrahedron")
    ):
        started = time.monotonic()
        mark = executor.session.SetUndoMark(
            nx.Session.MarkVisibility.Visible, "MCP development " + role + " mesh"
        )
        builder = None
        try:
            builder = manager.CreateMesh3dTetBuilder(None)
            assert element in builder.ElementType.GetElementTypeNames()
            builder.ElementType.ElementTypeName = element
            builder.ElementType.DestinationCollector.AutomaticMode = True
            builder.AutoSizeOption = False
            builder.PropertyTable.SetBaseScalarWithDataPropertyValue(
                "quad mesh overall edge size", 5.0, fem.UnitCollection.FindObject("MilliMeter")
            )
            builder.SelectionList.Add([body])
            meshes = list(builder.CommitMesh())
            builder.Destroy()
            builder = None
            actual = []
            for mesh in meshes:
                reader = manager.CreateMesh3dTetBuilder(mesh)
                try:
                    assert reader.ElementType.ElementTypeName == element
                    actual.append(
                        {
                            "name": mesh.Name,
                            "element_type": reader.ElementType.ElementTypeName,
                            "properties": read_properties(reader.PropertyTable, nx),
                        }
                    )
                finally:
                    reader.Destroy()
            record(
                role + "_mesh", {"meshes": actual, "elapsed_seconds": time.monotonic() - started}
            )
        except Exception as error:
            if builder:
                builder.Destroy()
            executor.session.UndoToMark(mark, None)
            record(
                role + "_mesh_failure",
                {"type": type(error).__name__, "nx_code": getattr(error, "ErrorCode", None)},
            )
            raise
    fid = executor._reference(fem, "part", fem, "FEM")["id"]
    record(
        "solid_material",
        executor._sim_material(
            fid,
            "Development aluminium",
            200.0,
            2700.0,
            900.0,
            "Assumed constant generic benchmark values",
            True,
        ),
    )
    collectors = list(manager.GetMeshCollectors())
    record("collectors", [{"name": c.Name, "type": c.CollectorNeutralType} for c in collectors])
    air = [c for c in collectors if c.CollectorNeutralType == "Fluid"]
    material = assign_fluid_material(
        executor.session,
        fem,
        air,
        "Development air",
        "Assumed constant room-temperature benchmark air",
        1.2,
        1.81e-5,
        0.0257,
        1005.0,
    )
    material["material"] = material["material"].Name
    record("air_material", material)
    for part in (fem, sim):
        status = part.Save(
            nx.BasePart.SaveComponents.FalseValue, nx.BasePart.CloseAfterSave.FalseValue
        )
        if status:
            status.Dispose()
    _, status = executor.session.Parts.SetDisplay(sim, False, False)
    if status:
        status.Dispose()
    executor.session.Parts.SetWork(sim)
    record(
        "authoring_complete",
        {
            "interfaces_validated": False,
            "boundary_conditions_complete": False,
            "solve_ready": False,
        },
    )
    return data

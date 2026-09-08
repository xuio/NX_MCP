"""Isolated generic finned solid/air geometry and coarse mesh; no solver launch."""


def run(executor, *, variant="baseline", mesh_size_mm=2.0, material_factory=None):
    import json
    import time

    import NXOpen as nx
    import NXOpen.CAE as cae
    import NXOpen.UF as uf

    from nx_mcp.simcenter.flow import attach_default_tables, create_initial_step
    from nx_mcp.simcenter.fluid_material import assign_fluid_material
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    if variant in ("stock_material", "stock_copy") and material_factory is None:
        raise ValueError("Stock-material diagnostic requires its explicit template factory")
    if material_factory is not None:
        if variant not in ("stock_material", "stock_copy"):
            raise ValueError(
                "Diagnostic material factory is restricted to the stock-material fixture"
            )
        assign_fluid_material = material_factory
    if (variant, mesh_size_mm) not in (
        ("baseline", 2.0),
        ("stock_material", 2.0),
        ("stock_copy", 2.0),
        ("material_contrast", 2.0),
        ("refined", 1.0),
        ("fine", 0.5),
        ("layer_coarse", 1.0),
        ("layer_fine", 1.0),
    ):
        raise ValueError("Select one of the bounded benchmark mesh levels")
    prefix = "finned_r1" if variant == "baseline" else "finned_" + variant + "_r1"
    root = executor.workspace.resolve(f"ui-benchmarks/E-finned-{variant}-20260908-r1")
    receipt = executor.workspace.resolve(f"ui-benchmarks/E-finned-{variant}-r1-build.json")
    resumed_cad = None
    previous_failure = None
    if root.exists() or receipt.exists():
        previous = json.loads(receipt.read_text())
        previous_failure = previous.get("failure")
        current = executor.session.Parts.BaseWork
        if (
            previous_failure is None
            or previous_failure.get("stage") != "CAD"
            or previous_failure.get("message")
            != "First parameter is invalid. Expecting double type, found int."
            or current.FullPath != str(root / f"{prefix}_geometry.prt")
            or list(current.Bodies)
            or list(current.Features)
        ):
            raise ValueError(
                "Existing fixture is not the verified empty CAD failure; inspect manually"
            )
        resumed_cad = current
    else:
        root.mkdir(parents=True)
    rows = {
        "previous_failure": previous_failure,
        "solver_launched": False,
        "acceptance": False,
        "mesh_size_mm": mesh_size_mm,
    }

    def record(key, value):
        rows[key] = value
        receipt.write_text(json.dumps(rows, indent=2))

    record(
        "intent",
        {"folder": str(root), "geometry": "20x10x2 mm base, two 20x1x4 mm fins, air to z=10 mm"},
    )
    started = time.monotonic()
    stage = "CAD"
    try:
        cad = resumed_cad or executor.session.Parts.NewBaseDisplay(
            str(root / f"{prefix}_geometry.prt"), nx.BasePart.Units.Millimeters
        )

        def block(origin, size, target=None, operation=None):
            builder = cad.Features.CreateBlockFeatureBuilder(None)
            try:
                builder.SetOriginAndLengths(
                    nx.Point3d(*map(float, origin)), *[str(x) for x in size]
                )
                if target is not None:
                    builder.SetBooleanOperationAndTarget(operation, target)
                feature = builder.CommitFeature()
                return list(feature.GetBodies())[0]
            finally:
                builder.Destroy()

        solid = block((0, 0, 0), (20, 10, 2))
        for y in (2, 7):
            solid = block((0, y, 2), (20, 1, 4), solid, nx.Features.Feature.BooleanType.Unite)
        air = block((0, 0, 2), (20, 10, 8))
        for y in (2, 7):
            air = block((0, y, 2), (20, 1, 4), air, nx.Features.Feature.BooleanType.Subtract)
        assert len(list(cad.Bodies)) == 2

        def save(part):
            status = part.Save(
                nx.BasePart.SaveComponents.FalseValue, nx.BasePart.CloseAfterSave.FalseValue
            )
            if status:
                status.Dispose()

        save(cad)
        stage = "FEM"
        fem = executor.session.Parts.NewBaseDisplay(
            str(root / f"{prefix}_mesh.fem"), nx.BasePart.Units.Millimeters
        )
        options = fem.NewFemCreationOptions()
        sync = fem.NewFemSynchronizeOptions()
        try:
            options.SetCadData(cad, "")
            options.SetSolverOptions(
                "NX MULTIPHYSICS",
                "Coupled Thermal-Flow",
                cae.BaseFemPart.AxisymAbstractionType.NotSet,
            )
            options.SetGeometryOptions(cae.FemCreationOptions.UseBodiesOption.AllBodies, [], sync)
            fem.FinalizeCreation(options)
        finally:
            options.Dispose()
        sf = uf.UFSession.GetUFSession().Sf
        bodies = sorted(fem.Bodies, key=lambda b: sf.BodyAskBoundingBox(b.Tag)[2])
        assert len(bodies) == 2
        geometry = []
        for body, expected, role in zip(bodies, (560.0, 1440.0), ("solid", "air"), strict=True):
            volume = sf.BodyAskVolumeAndCentroid(body.Tag)[0]
            assert abs(volume - expected) < 1e-5, (role, volume)
            geometry.append(
                {
                    "role": role,
                    "volume_mm3": volume,
                    "bounds_mm": list(sf.BodyAskBoundingBox(body.Tag)),
                }
            )
        record("geometry", geometry)
        record("geometry_seconds", time.monotonic() - started)
        stage = "mesh"
        manager = fem.BaseFEModel.MeshManager
        mesh_started = time.monotonic()
        for body, role, element in zip(
            bodies,
            ("solid", "air"),
            ("Linear Tetrahedron", "Fluid Linear Tetrahedron"),
            strict=True,
        ):
            if role == "air" and variant.startswith("layer_"):
                from nx_mcp.simcenter.boundary_layers import create_boundary_layers

                _, tags = sf.BodyAskFaces(body.Tag)
                walls = [
                    nx.TaggedObjectManager.GetTaggedObject(tag)
                    for tag in tags
                    if abs(sf.FaceAskBoundingBox(tag)[3] - sf.FaceAskBoundingBox(tag)[0] - 20.0)
                    < 1e-6
                ]
                assert len(walls) == 12, len(walls)
                layer = create_boundary_layers(
                    executor.session,
                    fem,
                    walls,
                    first_layer_mm=0.05 if variant == "layer_coarse" else 0.025,
                    layers=8,
                    growth_rate=1.2,
                )
                layer["control"] = layer["control"].Name
                record("layer_control_before_mesh", layer)
            builder = manager.CreateMesh3dTetBuilder(None)
            try:
                assert element in builder.ElementType.GetElementTypeNames()
                builder.ElementType.ElementTypeName = element
                builder.ElementType.DestinationCollector.AutomaticMode = True
                builder.AutoSizeOption = False
                builder.PropertyTable.SetBaseScalarWithDataPropertyValue(
                    "quad mesh overall edge size",
                    mesh_size_mm,
                    fem.UnitCollection.FindObject("MilliMeter"),
                )
                builder.SelectionList.Add([body])
                meshes = list(builder.CommitMesh())
                record(role + "_meshes", [m.Name for m in meshes])
            finally:
                builder.Destroy()
        record("mesh_seconds", time.monotonic() - mesh_started)
        if variant.startswith("layer_"):
            element_map = fem.BaseFEModel.FeelementLabelMap
            cardinalities = {}
            try:
                label = 0
                for _ in range(element_map.NumElements):
                    label = element_map.AskNextElementLabel(label)
                    count = str(len(element_map.GetElement(label).GetNodes()))
                    cardinalities[count] = cardinalities.get(count, 0) + 1
            finally:
                element_map.Dispose()
            record("element_node_cardinalities", cardinalities)
            assert cardinalities.get("6", 0) > 0, "No generated wedge layer elements"

        stage = "materials"
        fid = executor._reference(fem, "part", fem, "FEM")["id"]
        record(
            "solid_material",
            executor._sim_material(
                fid,
                "Generic aluminium",
                200.0,
                2700.0,
                900.0,
                "Assumed constant generic infrastructure benchmark",
                True,
            ),
        )
        collectors = [c for c in manager.GetMeshCollectors() if c.CollectorNeutralType == "Fluid"]
        contrast = variant == "material_contrast"
        material = assign_fluid_material(
            executor.session,
            fem,
            collectors,
            "Generic air",
            "Synthetic translator diagnostic, not physical air"
            if contrast
            else "Assumed constant benchmark air",
            2.0 if contrast else 1.2,
            3e-5 if contrast else 1.81e-5,
            0.05 if contrast else 0.0257,
            1200.0 if contrast else 1005.0,
        )
        material["material"] = material["material"].Name
        record("air_material", material)
        save(fem)
        stage = "SIM"
        sim = executor.session.Parts.NewBaseDisplay(
            str(root / f"{prefix}_analysis.sim"), nx.BasePart.Units.Millimeters
        )
        sim.FinalizeCreation(fem, ["NX MCP generic finned coupled benchmark"])
        solution = sim.Simulation.CreateSolution(
            "NX MULTIPHYSICS",
            "Coupled Thermal-Flow",
            "Thermal-Flow",
            "Finned coupled benchmark",
            cae.SimSimulation.AxisymAbstractionType.NotSet,
        )
        assert solution.AnalysisType == "Coupled Thermal-Flow"
        record("step", create_initial_step(executor.session, sim, "Finned steady"))
        record("tables", attach_default_tables(executor.session, sim, "Finned"))
        save(sim)
        record("total_seconds", time.monotonic() - started)
        record("completed_setup", True)
        record(
            "remaining",
            [
                "boundary authoring and membership",
                "interface/property audit",
                "bounded solve",
                "refinement and acceptance",
            ],
        )
        return rows
    except Exception as error:
        record(
            "failure",
            {
                "stage": stage,
                "type": type(error).__name__,
                "message": str(error),
                "nx_code": getattr(error, "ErrorCode", None),
                "retained_partial_fixture": True,
            },
        )
        raise

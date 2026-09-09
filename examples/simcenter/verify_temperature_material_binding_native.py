def run(executor):
    import NXOpen as nx
    import NXOpen.Fields as fields

    from nx_mcp.simcenter import scalar_tables
    from nx_mcp.simcenter.properties import read_properties

    session = executor.session
    sim = session.Parts.BaseWork
    assert "T-heat-recovery-20260909-r1" in sim.FullPath
    fem = sim.FemPart
    flags = {p.FullPath: bool(p.IsModified) for p in session.Parts}
    _, status = session.Parts.SetDisplay(fem, False, False)
    if status:
        status.Dispose()
    session.Parts.SetWork(fem)
    before = {
        "materials": [int(m.Tag) for m in fem.MaterialManager.PhysicalMaterials],
        "fields": [int(f.Tag) for f in fem.FieldManager.Fields],
        "expressions": [int(e.Tag) for e in fem.Expressions],
    }
    mark = session.SetUndoMark(
        nx.Session.MarkVisibility.Invisible, "Temperature-dependent material binding probe"
    )
    builder = None
    result = {}
    try:
        builder = fem.MaterialManager.PhysicalMaterials.CreatePhysicalMaterialBuilder(
            nx.PhysicalMaterial.Type.Isotropic
        )
        builder.Name = "MCP_TEMPDEP_PROBE"
        builder.Description = "Bounded thermal material API experiment"
        builder.AddToMaterialLibraryToggle = False
        definitions = {}
        for key, quantity, ys in [
            ("ThermalConductivity", "conductivity", [100, 150, 200]),
            ("SpecificHeat", "heat_capacity", [800, 900, 1000]),
        ]:
            m = {
                "name": "MCP_" + key,
                "axis": "temperature",
                "quantity": quantity,
                "samples": [[273.15, ys[0]], [293.15, ys[1]], [313.15, ys[2]]],
                "provenance": "Generic temperature-material API fixture",
            }
            unit = fem.UnitCollection.FindObject(scalar_tables.VALUES[quantity][0])
            celsius = fem.UnitCollection.FindObject("Celsius")
            kelvin = fem.UnitCollection.FindObject("Kelvin")
            data = []
            for x, y in m["samples"]:
                data.extend([fem.UnitCollection.Convert(kelvin, celsius, float(x)), float(y)])
            table = fem.FieldManager.CreateFieldTableFromData(
                m["name"], celsius, unit, fields.FieldVariable.ValueType.Real, data
            )
            table.InterpolationMethod = fields.FieldEvaluator.InterpolationEnum.Linear1d
            table.ValuesOutsideTableInterpolation = (
                fields.FieldEvaluator.ValuesOutsideTableInterpolationEnum.Undefined
            )
            table.LinearLogOption = fields.FieldEvaluator.LinearLogOptionEnum.LinearLinear
            header, chunks = scalar_tables.encode(m)
            for i, chunk in enumerate(chunks):
                table.SetUserAttribute(scalar_tables.DATA, i, chunk, nx.Update.Option.Now)
            table.SetUserAttribute(scalar_tables.HEADER, -1, header, nx.Update.Option.Now)
            definitions[key] = scalar_tables.inspect(fem, table)
            wrapper = fem.FieldManager.CreateScalarFieldWrapperWithField(table, 1.0)
            builder.PropertyTable.SetScalarFieldWrapperPropertyValue(key, wrapper)
        expr = fem.Expressions.CreateSystemNumberExpression(
            "2700", fem.UnitCollection.FindObject("KilogramPerCubicMeter")
        )
        builder.PropertyTable.SetScalarFieldWrapperPropertyValue(
            "MassDensityConstant", fem.FieldManager.CreateScalarFieldWrapperWithExpression(expr)
        )
        material = builder.Commit()
        builder.Destroy()
        builder = None
        props = read_properties(material.GetPropTable(), nx)
        for key in definitions:
            prop = next(p for p in props if p["name"] == key)
            assert (
                prop["field_scale"] == 1.0
                and prop["field_definition"]["manifest"] == definitions[key]["manifest"]
            ), prop
        result = {
            "material_properties": [
                p
                for p in props
                if p.get("name")
                in [
                    "ThermalConductivity",
                    "ThermalConductivityControl",
                    "SpecificHeat",
                    "SpecificHeatControl",
                    "MassDensityConstant",
                ]
            ],
            "definitions": definitions,
            "committed_readback_verified": True,
            "assignment_verified": False,
            "export_verified": False,
            "solver_launched": False,
        }
    finally:
        if builder:
            builder.Destroy()
        session.UndoToMark(mark, None)
        session.DeleteUndoMark(mark, None)
        after = {
            "materials": [int(m.Tag) for m in fem.MaterialManager.PhysicalMaterials],
            "fields": [int(f.Tag) for f in fem.FieldManager.Fields],
            "expressions": [int(e.Tag) for e in fem.Expressions],
        }
        assert before == after, (before, after)
        sid = executor._reference(sim, "part", sim, "SIM")["id"]
        executor._sim_activate(sid)
        assert flags == {p.FullPath: bool(p.IsModified) for p in session.Parts}
    result["rollback_verified"] = True
    return result

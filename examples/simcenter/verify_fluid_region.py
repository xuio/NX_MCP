def run(executor):
    import importlib
    import json
    from pathlib import Path

    import nx_mcp.simcenter.fluid_domain as domain

    importlib.reload(domain)
    s = executor.session
    fem = s.Parts.BaseWork
    if "D-cavity-documents-20260908-r2" not in fem.FullPath or type(fem).__name__ != "FemPart":
        raise ValueError("Requires isolated cavity FEM")
    cad = fem.AssociatedCadPart
    units = [
        cad.UnitCollection.FindObject(n)
        for n in ["SquareMilliMeter", "CubicMilliMeter", "Kilogram", "MilliMeter", "Newton"]
    ]
    mass = cad.MeasureManager.NewMassProperties(units, 0.999, list(cad.Bodies))
    try:
        mass.InformationUnit = executor.nxopen.MeasureBodies.AnalysisUnit.KilogramMillimeter
        volume = float(mass.Volume)
    finally:
        mass.Dispose()
    if abs(volume - 14408) > 0.01:
        raise ValueError("Source cavity volume mismatch")
    record = Path(fem.FullPath).parent / "fluid-region-cavity-03.json"
    if record.exists():
        return {"replayed": True, "receipt": json.loads(record.read_text())}
    result = domain.create_wrapped_region(
        s, fem, list(fem.Bodies), [81.0, 11.0, 11.0], 2.0, "Duct air region"
    )
    recipe = result.pop("recipe")
    bodies = result.pop("bodies")
    result.update(
        source_solid_volume_mm3=volume,
        expected_cavity_volume_mm3=64000.0,
        recipe_tag=int(recipe.Tag),
        bodies=[{"tag": int(b.Tag), "type": type(b).__name__} for b in bodies],
    )
    with record.open("x") as f:
        json.dump(result, f, indent=2)
    return result

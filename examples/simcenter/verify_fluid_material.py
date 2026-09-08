"""Assign assumed constant air properties to the isolated duct cavity."""


def run(executor):
    import importlib
    import json
    from pathlib import Path

    import NXOpen.CAE as cae

    import nx_mcp.simcenter.fluid_material as fluid

    importlib.reload(fluid)
    s = executor.session
    fem = next(
        p
        for p in s.Parts
        if isinstance(p, cae.FemPart) and "D-cavity-documents-20260908-r2" in p.FullPath
    )
    receipt = Path(fem.FullPath).parent / "fluid-material-01.json"
    if receipt.exists():
        return {"replayed": True, "receipt": json.loads(receipt.read_text())}
    _, status = s.Parts.SetDisplay(fem, False, False)
    if status:
        status.Dispose()
    s.Parts.SetWork(fem)
    result = fluid.assign_fluid_material(
        s,
        fem,
        list(fem.BaseFEModel.MeshManager.GetMeshCollectors()),
        "Benchmark constant air",
        "Assumed benchmark values near room temperature; constant density and transport properties, not measured product data. Solver control interpretation pending.",
        1.2,
        1.81e-5,
        0.0257,
        1005.0,
    )
    material = result.pop("material")
    result["material_name"] = material.Name
    with receipt.open("x") as stream:
        json.dump(result, stream, indent=2)
    return result

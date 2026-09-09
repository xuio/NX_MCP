def run(executor):
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    path = executor.workspace.resolve("ui-benchmarks/public-multibody-20260909-r1/input17.prt")
    if path.exists():
        raise ValueError("Fixture already exists; inspect existing receipt, do not recreate")
    path.parent.mkdir(parents=True, exist_ok=True)
    nx = executor.nxopen
    loaded = [p for p in executor.session.Parts if p.FullPath.casefold() == str(path).casefold()]
    if loaded:
        if len(loaded) != 1 or list(loaded[0].Bodies) or list(loaded[0].Features):
            raise ValueError("Partial CAD contains objects; inspect instead of retrying")
        cad = loaded[0]
    else:
        cad = executor.session.Parts.NewBaseDisplay(str(path), nx.BasePart.Units.Millimeters)
    for index in range(17):
        name = "Region " + str(index)
        builder = cad.Features.CreateBlockFeatureBuilder(None)
        try:
            builder.SetOriginAndLengths(nx.Point3d(float(index * 5), 0.0, 0.0), "3", "3", "3")
            feature = builder.CommitFeature()
            feature.SetName(name)
        finally:
            builder.Destroy()
    status = cad.Save(nx.BasePart.SaveComponents.FalseValue, nx.BasePart.CloseAfterSave.FalseValue)
    if status:
        status.Dispose()
    cad.ModelingViews.WorkView.Fit()
    cad.ModelingViews.WorkView.UpdateDisplay()
    return {
        "cad": executor._reference(cad, "part", cad, "CAD"),
        "path": str(path),
        "body_count": len(list(cad.Bodies)),
        "solver_launched": False,
    }

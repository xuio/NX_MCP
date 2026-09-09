def run(executor):
    import importlib
    import types
    from nx_mcp import hardened
    from nx_mcp.simcenter import native, server, environment, analysis_documents
    from nx_mcp.simcenter.solver_guard import require_solver_idle
    require_solver_idle()
    for module in (server, environment, analysis_documents, native):
        importlib.reload(module)
    for name in ('_sim_environment', '_sim_create_analysis'):
        method=types.MethodType(getattr(native.SimcenterMixin,name),executor)
        setattr(executor,name,method)
        executor._handlers['nx'+name]=method
        hardened.NON_MODEL.add('nx'+name)
    path=executor.workspace.resolve('ui-benchmarks/public-user-cad-20260909-r1/input_r1.prt')
    if path.exists():
        raise ValueError('Fixture already exists; inspect existing receipt, do not recreate')
    path.parent.mkdir(parents=True,exist_ok=True)
    nx=executor.nxopen
    loaded=[p for p in executor.session.Parts if p.FullPath.casefold()==str(path).casefold()]
    if loaded:
        if len(loaded)!=1 or list(loaded[0].Bodies) or list(loaded[0].Features):
            raise ValueError('Partial CAD contains objects; inspect instead of retrying')
        cad=loaded[0]
    else:
        cad=executor.session.Parts.NewBaseDisplay(str(path),nx.BasePart.Units.Millimeters)
    for name,z,height in [('Heated solid',0,2),('Air region',2,8)]:
        builder=cad.Features.CreateBlockFeatureBuilder(None)
        try:
            builder.SetOriginAndLengths(nx.Point3d(0.0,0.0,float(z)),'20','10',str(height))
            feature=builder.CommitFeature()
            feature.SetName(name)
        finally:
            builder.Destroy()
    status=cad.Save(nx.BasePart.SaveComponents.FalseValue,nx.BasePart.CloseAfterSave.FalseValue)
    if status:status.Dispose()
    cad.ModelingViews.WorkView.Fit()
    cad.ModelingViews.WorkView.UpdateDisplay()
    return {'cad':executor._reference(cad,'part',cad,'CAD'),'path':str(path),'body_count':len(list(cad.Bodies)),'solver_launched':False}

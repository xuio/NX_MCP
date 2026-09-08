def run(executor):
    import importlib,runpy,types
    from pathlib import Path
    from nx_mcp import interactive,ui_document
    host=interactive._host
    parts=list(executor.session.Parts)
    before={p.FullPath:bool(p.IsModified) for p in parts}
    importlib.reload(ui_document)
    updated=runpy.run_path(interactive.__file__)['InteractiveHost']
    host.panel_text=types.MethodType(updated.panel_text,host)
    host.status=types.MethodType(updated.status,host)
    executor.session.ListingWindow.CloseWindow()
    part=executor.session.Parts.BaseDisplay
    part.ModelingViews.WorkView.Fit()
    part.ModelingViews.WorkView.UpdateDisplay()
    host.publish()
    after={p.FullPath:bool(p.IsModified) for p in parts}
    capture=runpy.run_path(r'Z:\nx-mcp-integration\simcenter-discovery\capture-ui-via-nx.py')['run'](executor)
    return {'work_document':host.status()['work_document'],'visible_document':host.status()['visible_document'],'capture':capture,'modified_flags_preserved':before==after,'report_closed':True,'view_fitted':True,'restarted':False}

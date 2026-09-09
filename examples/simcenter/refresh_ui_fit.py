def run(executor):
    import importlib
    import runpy
    import types

    from nx_mcp import interactive, ui_document

    host = interactive._host
    before = [(p.FullPath, bool(p.IsModified)) for p in executor.session.Parts]
    previous = {
        "instance_execute": "execute" in host.__dict__,
        "module": host.execute.__func__.__module__,
        "name": host.execute.__func__.__qualname__,
    }
    importlib.reload(ui_document)
    updated = runpy.run_path(interactive.__file__)["InteractiveHost"]
    host.execute = types.MethodType(updated.execute, host)
    host.dispatcher._executor = host.execute
    executor.session.ListingWindow.CloseWindow()
    result = {}
    ui_document.refresh_model_view(executor.session, "nx_activate_part", result)
    after = [(p.FullPath, bool(p.IsModified)) for p in executor.session.Parts]
    return {
        "previous": previous,
        "installed": "refresh_model_view" in host.execute.__func__.__code__.co_names,
        "display": executor.session.Parts.BaseDisplay.FullPath,
        "work": executor.session.Parts.BaseWork.FullPath,
        "documents_unchanged": before == after,
        "refresh": result,
    }

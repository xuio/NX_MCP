"""UI-thread-only document caption; never activates, saves or regenerates a part."""


def document_info(part):
    from pathlib import PureWindowsPath

    if part is None:
        return {"path": None, "name": "No document", "modified": False}
    path = part.FullPath
    return {
        "path": path,
        "name": PureWindowsPath(path).name or part.Name,
        "modified": bool(part.IsModified),
    }


def visible_document(session):
    return document_info(session.Parts.BaseDisplay)


def update_document_caption(host):
    context = visible_document(host.session)
    host._visible_document = context
    work = document_info(host.session.Parts.BaseWork)
    host._work_document = work
    title = "NX MCP — " + context["name"] + (" *" if context["modified"] else "")
    if work != context:
        title += " | Work: " + work["name"] + (" *" if work["modified"] else "")
    host.panel.user.SetWindowTextW(host.panel.hwnd, title)


def refresh_model_view(session, method, result):
    """Fit visible geometry after mutations, preserving explicit camera commands."""
    from nx_mcp.hardened import READ_ONLY

    if method in READ_ONLY:
        return
    try:
        part = getattr(session.Parts, "BaseDisplay", None)
        if part is None:
            part = getattr(session.Parts, "Display", None)
        sheet = getattr(getattr(part, "DrawingSheets", None), "CurrentDrawingSheet", None)
        if part is None or sheet is not None:
            return
        view = part.ModelingViews.WorkView
        if method not in {"nx_set_camera", "nx_fit_view"}:
            try:
                view.Fit()
            except Exception as exc:
                result.setdefault("warnings", []).append("View fit: " + str(exc))
        view.UpdateDisplay()
    except Exception as exc:
        # Presentation failure must not invite a retry of committed geometry.
        result.setdefault("warnings", []).append("View refresh: " + str(exc))

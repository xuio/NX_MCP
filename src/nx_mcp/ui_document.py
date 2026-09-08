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

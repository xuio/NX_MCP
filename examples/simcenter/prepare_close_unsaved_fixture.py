"""Mark only the disposable public-open SIM dirty for close-guard acceptance."""


def run(executor):
    import NXOpen as nx

    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    part = next(p for p in executor.session.Parts if p.FullPath.endswith("public_open_r1.sim"))
    if "scenario-multi-mcp-20260908-r1" not in part.FullPath:
        raise ValueError("Only the isolated lifecycle fixture may be annotated")
    before = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts if p != part}
    mark = executor.session.SetUndoMark(
        nx.Session.MarkVisibility.Visible, "NX MCP close safety fixture"
    )
    try:
        part.SetUserAttribute(
            "NX_MCP_CLOSE_SAFETY_FIXTURE", -1, "unsaved-test-r1", nx.Update.Option.Now
        )
        assert part.GetStringUserAttribute("NX_MCP_CLOSE_SAFETY_FIXTURE", -1) == "unsaved-test-r1"
        assert part.IsModified
    except Exception:
        executor.session.UndoToMark(mark, None)
        raise
    assert {p.FullPath: bool(p.IsModified) for p in executor.session.Parts if p != part} == before
    return {
        "path": part.FullPath,
        "modified": bool(part.IsModified),
        "other_flags_preserved": True,
        "saved": False,
    }

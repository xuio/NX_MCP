"""Measure same-path native reopen after saving only the isolated probe copy."""


def run(executor):
    import NXOpen as nx

    from nx_mcp.simcenter.documents import save_document
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    session = executor.session
    part = session.Parts.BaseWork
    path = part.FullPath
    if not path.endswith("reopen_modified_probe_r1.sim"):
        raise ValueError("Only the disposable diagnostic copy may be saved/closed")
    others = {p.FullPath: bool(p.IsModified) for p in session.Parts if p != part}
    stages = []
    saves = []
    for cycle in range(2):
        stages.append({"cycle": cycle, "stage": "before_save", "modified": bool(part.IsModified)})
        saves.append(save_document(session, executor.workspace, part))
        stages.append({"cycle": cycle, "stage": "after_save", "modified": bool(part.IsModified)})
        assert not part.IsModified
        old_id = executor._part_id(part)
        part.Close(
            nx.BasePart.CloseWholeTree.FalseValue, nx.BasePart.CloseModified.CloseModified, None
        )
        executor.objects.invalidate_part(old_id)
        part, status = session.Parts.OpenBaseDisplay(path)
        stages.append(
            {"cycle": cycle, "stage": "OpenBaseDisplay_returned", "modified": bool(part.IsModified)}
        )
        if status:
            status.Dispose()
        session.Parts.SetWork(part)
        stages.append({"cycle": cycle, "stage": "SetWork", "modified": bool(part.IsModified)})
    assert {p.FullPath: bool(p.IsModified) for p in session.Parts if p != part} == others
    return {
        "path": path,
        "stages": stages,
        "saves": saves,
        "other_flags_preserved": True,
        "scope": "Same-path reopen before property/target inspection; probe copy only",
    }

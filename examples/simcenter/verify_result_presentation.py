def run(executor):
    import hashlib
    import importlib
    from pathlib import Path

    from nx_mcp.simcenter import postviews

    importlib.reload(postviews)
    session = executor.session
    sim = session.Parts.BaseWork
    assert sim.FullPath.endswith("contact_explicit_r1.sim")
    before = {p.FullPath: bool(p.IsModified) for p in session.Parts}
    result = postviews.show_temperature(
        session, sim, executor._sim_post_result_handles, name="MCP current contact temperature"
    )
    result["modified_flags_preserved"] = before == {
        p.FullPath: bool(p.IsModified) for p in session.Parts
    }
    result["work_path"] = session.Parts.BaseWork.FullPath
    result["display_path"] = session.Parts.BaseDisplay.FullPath
    result["source_sha256"] = hashlib.sha256(Path(postviews.__file__).read_bytes()).hexdigest()
    return result

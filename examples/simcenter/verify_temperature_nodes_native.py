def run(executor):
    import importlib

    from nx_mcp.simcenter import nodal_results
    from nx_mcp.simcenter.results import temperature_extrema

    importlib.reload(nodal_results)
    s = executor.session
    sim = s.Parts.BaseWork
    assert sim.FullPath.endswith("mesh_guard_positive_r1.sim")
    flags = [(p.FullPath, bool(p.IsModified)) for p in s.Parts]
    views = list(s.Post.GetPostviewIds())
    pages = [nodal_results.temperature_nodes(s, sim, offset=o, limit=17) for o in (0, 17, 34, 51)]
    rows = [r for p in pages for r in p["items"]]
    assert len(rows) == 45 and [r["index"] for r in rows] == list(range(1, 46))
    extrema = temperature_extrema(s, sim)
    assert min(r["temperature"] for r in rows) == extrema["minimum"]
    assert max(r["temperature"] for r in rows) == extrema["maximum"]
    bounds = [
        [min(r["coordinates"][i] for r in rows), max(r["coordinates"][i] for r in rows)]
        for i in range(3)
    ]
    assert bounds == [[0.0, 10.0]] * 3
    assert flags == [(p.FullPath, bool(p.IsModified)) for p in s.Parts]
    assert views == list(s.Post.GetPostviewIds())
    return {
        "passed": True,
        "pages": pages,
        "bounds": bounds,
        "extrema": extrema,
        "document_flags_preserved": True,
        "postviews_preserved": True,
        "solver_launched": False,
    }

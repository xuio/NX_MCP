def run(executor):
    from nx_mcp.simcenter.region_results import temperature_regions

    s = executor.session
    sims = [
        p
        for p in s.Parts
        if p.FullPath.endswith(("mesh_guard_positive_r1.sim", "contact_explicit_r1.sim"))
    ]
    assert len(sims) == 2
    flags = [(p.FullPath, bool(p.IsModified)) for p in s.Parts]
    views = list(s.Post.GetPostviewIds())
    rows = []
    for sim in sims:
        region = temperature_regions(s, sim, dimension="3d")
        surface = temperature_regions(s, sim, dimension="2d")
        expected = 2 if sim.FullPath.endswith("contact_explicit_r1.sim") else 1
        assert len(region["items"]) == expected
        assert all(r["node_count"] == 45 and r["element_count"] == 100 for r in region["items"])
        assert region["total"] == expected and region["next_offset"] is None
        rows.append({"path": sim.FullPath, "volume_groups": region, "surface_groups": surface})
    assert flags == [(p.FullPath, bool(p.IsModified)) for p in s.Parts]
    assert views == list(s.Post.GetPostviewIds())
    return {
        "passed": True,
        "cases": rows,
        "document_flags_preserved": True,
        "postviews_preserved": True,
        "solver_launched": False,
    }

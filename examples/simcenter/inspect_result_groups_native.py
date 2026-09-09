def run(executor):
    import NXOpen.CAE as cae

    from nx_mcp.simcenter.results import acquire_result

    s = executor.session
    sims = [
        p
        for p in s.Parts
        if p.FullPath.endswith(("mesh_guard_positive_r1.sim", "contact_explicit_r1.sim"))
    ]
    assert sims
    flags = [(p.FullPath, bool(p.IsModified)) for p in s.Parts]
    views = list(s.Post.GetPostviewIds())
    rows = []
    for sim in sims:
        result, owned = acquire_result(s, sim)
        try:
            row = {"path": sim.FullPath, "groups": [], "meshes": []}
            for kind in ("ThreeDimensional", "TwoDimensional"):
                enum = getattr(cae.Result.GroupContainer, kind)
                count = result.AskNumGroupsInContainer(enum)
                assert count <= 20
                for i in range(count):
                    ids = list(result.AskNumElementsOfGroup(enum, i))
                    assert len(ids) <= 5000
                    nodes = sorted({int(n) for e in ids for n in result.AskElementNodes(e)})
                    coords = result.AskNodeCoordinates(nodes)
                    row["groups"].append(
                        {
                            "dimension": kind,
                            "index": i,
                            "elements": len(ids),
                            "element_indices": ids,
                            "nodes": len(nodes),
                            "bounds": [
                                [
                                    min(getattr(p, a) for p in coords),
                                    max(getattr(p, a) for p in coords),
                                ]
                                for a in ("X", "Y", "Z")
                            ]
                            if coords
                            else None,
                        }
                    )
            for mesh in result.GetMeshes():
                row["meshes"].append(
                    {
                        "name": mesh.Name,
                        "dimension": str(mesh.MeshDimension),
                        "elements": mesh.NumElements,
                        "material": mesh.MaterialDescription,
                        "property": mesh.PropertyDescription,
                    }
                )
            rows.append(row)
        finally:
            if owned:
                s.ResultManager.DeleteResult(result)
    assert flags == [(p.FullPath, bool(p.IsModified)) for p in s.Parts]
    assert views == list(s.Post.GetPostviewIds())
    return {
        "passed": True,
        "cases": rows,
        "document_flags_preserved": True,
        "postviews_preserved": True,
        "solver_launched": False,
    }

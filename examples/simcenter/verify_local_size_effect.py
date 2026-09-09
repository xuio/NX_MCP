def run(executor):
    from collections import Counter

    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    fem = executor.session.Parts.BaseWork
    assert type(fem).__name__ == "FemPart" and "L-face-size-20260909-r1" in fem.FullPath
    flags = [(p.FullPath, bool(p.IsModified)) for p in executor.session.Parts]
    elements = fem.BaseFEModel.FeelementLabelMap
    counts = Counter()
    plane_nodes = {"baseline": set(), "local_size": set()}
    try:
        label = 0
        for _ in range(elements.NumElements):
            label = elements.AskNextElementLabel(label)
            nodes = list(elements.GetElement(label).GetNodes())
            xs = [node.Coordinates.X for node in nodes]
            group = "baseline" if max(xs) < 15 else "local_size"
            assert (
                (min(xs) >= -1e-7 and max(xs) <= 10 + 1e-7)
                if group == "baseline"
                else (min(xs) >= 20 - 1e-7 and max(xs) <= 30 + 1e-7)
            )
            counts[group] += 1
            for node, x in zip(nodes, xs, strict=True):
                if abs(x - (0 if group == "baseline" else 20)) < 1e-7:
                    plane_nodes[group].add(int(node.Tag))
        total = elements.NumElements
    finally:
        elements.Dispose()
    assert counts["local_size"] > counts["baseline"] > 0
    plane_counts = {key: len(value) for key, value in plane_nodes.items()}
    assert plane_counts["local_size"] > plane_counts["baseline"] > 0
    assert flags == [(p.FullPath, bool(p.IsModified)) for p in executor.session.Parts]
    return {
        "document": fem.FullPath,
        "element_count": total,
        "elements_per_block": dict(counts),
        "nodes_on_corresponding_xmin_faces": plane_counts,
        "global_size_mm": 5,
        "local_face_size_mm": 1,
        "geometry": "two identical disjoint 10 mm cubes",
        "effect_verified": "more elements and more nodes on the selected refined face than its counterpart",
        "flags_unchanged": True,
        "solver_launched": False,
        "convergence": "not_established",
    }

def run(executor):
    import importlib
    from collections import Counter

    from nx_mcp.simcenter import mesh_plan

    importlib.reload(mesh_plan)
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    fem = executor.session.Parts.BaseWork
    assert "M-mixed-mesh-20260909-r1" in fem.FullPath and type(fem).__name__ == "FemPart"
    flags = [(p.FullPath, bool(p.IsModified)) for p in executor.session.Parts]
    elements = fem.BaseFEModel.FeelementLabelMap
    histogram = Counter()
    try:
        label = 0
        for _ in range(elements.NumElements):
            label = elements.AskNextElementLabel(label)
            count = len(elements.GetElement(label).GetNodes())
            histogram[str(count)] += 1
        total = elements.NumElements
    finally:
        elements.Dispose()
    actual_counts = mesh_plan.mesh_counts(fem)
    assert actual_counts == {"elements": 529, "nodes": 281}
    assert total == 529 and histogram["6"] > 0
    assert flags == [(p.FullPath, bool(p.IsModified)) for p in executor.session.Parts]
    return {
        "document": fem.FullPath,
        "element_count": total,
        "element_node_cardinalities": dict(histogram),
        "six_node_elements_present": True,
        "scope": "Topology count in saved/reopened mixed linear mesh; not thermal/flow convergence",
        "flags_unchanged": True,
        "solver_launched": False,
    }

"""Native diagnostic check and bounded connectivity export; no repair is performed."""


def run(executor):
    import json
    from pathlib import Path

    fem = executor.session.Parts.BaseWork
    if "D-cavity-documents-20260908-r2" not in fem.FullPath:
        raise ValueError("Requires isolated cavity FEM")
    meshes = list(fem.BaseFEModel.MeshManager.GetMeshes())
    if len(meshes) != 1:
        raise ValueError("Requires one benchmark mesh")
    out = {}
    builder = fem.ModelCheckMgr.CreateElementQualityCheckBuilder()
    results = None
    try:
        builder.SelectionList.Add(meshes)
        results = builder.ExecuteCheck()
        out["native_check"] = {
            "element_count": results.ElementTestCount,
            "scope": str(builder.CheckScopeOption),
            "tests": [
                {
                    "type": str(t.TestType),
                    "count": t.TestCount,
                    "errors": t.ErrorCount,
                    "warnings": t.WarnedCount,
                    "worst_value": t.WorstTestValue if t.HasTestValue else None,
                }
                for t in results.GetTestSummary()
            ],
        }
    finally:
        if results is not None:
            results.Dispose()
        builder.Destroy()
    element_map = fem.BaseFEModel.FeelementLabelMap
    data = []
    try:
        if element_map.NumElements > 10000:
            raise ValueError("Fixture audit limit exceeded")
        label = 0
        for _ in range(element_map.NumElements):
            label = element_map.AskNextElementLabel(label)
            element = element_map.GetElement(label)
            nodes = element.GetNodes()
            data.append(
                {
                    "label": label,
                    "nodes": [
                        {
                            "label": n.Label,
                            "xyz": [n.Coordinates.X, n.Coordinates.Y, n.Coordinates.Z],
                        }
                        for n in nodes
                    ],
                }
            )
    finally:
        element_map.Dispose()
    path = Path(r"Z:\nx-mcp-integration\simcenter-discovery\fluid-mesh-connectivity.json")
    path.write_text(json.dumps({"units": "mm", "frame": "FEM_absolute", "elements": data}))
    out["connectivity_path"] = str(path)
    out["connectivity_elements"] = len(data)
    out["repair_attempted"] = False
    return out

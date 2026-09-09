def run(executor):
    from types import SimpleNamespace

    from nx_mcp.simcenter.remesh import settings

    session = executor.session
    sim = next(
        p
        for p in session.Parts
        if type(p).__name__ == "SimPart" and "U-sim-update-20260909-r1" in p.FullPath
    )
    fem = sim.FemPart
    before = [(p.FullPath, bool(p.IsModified)) for p in session.Parts]

    def raw_counts(part):
        e = n = None
        try:
            e = part.BaseFEModel.FeelementLabelMap
            n = part.BaseFEModel.FenodeLabelMap
            return {"elements": e.NumElements, "nodes": n.NumNodes}
        finally:
            try:
                if n is not None:
                    n.Dispose()
            finally:
                if e is not None:
                    e.Dispose()

    result = {
        "work_path": getattr(session.Parts.BaseWork, "FullPath", None),
        "display_path": session.Parts.BaseDisplay.FullPath,
        "fem_path": fem.FullPath,
        "fem_counts": raw_counts(fem),
        "sim_counts": raw_counts(SimpleNamespace(BaseFEModel=sim.Simulation.Femodel)),
        "mesh_settings": [
            settings(fem.BaseFEModel.MeshManager, m)
            for m in fem.BaseFEModel.MeshManager.GetMeshes()
        ],
        "fem_modified": bool(fem.IsModified),
        "sim_modified": bool(sim.IsModified),
        "update_pending": fem.BaseFEModel.AskUpdatePending(),
        "solver_launched": False,
    }
    result["flags_changed_by_inspection"] = before != [
        (p.FullPath, bool(p.IsModified)) for p in session.Parts
    ]
    return result

def run(executor):
    import importlib

    import nx_mcp.simcenter.quality as quality

    importlib.reload(quality)
    fem = executor.session.Parts.BaseWork
    if "D-cavity-documents-20260908-r2" not in fem.FullPath:
        raise ValueError("Requires cavity FEM")
    return quality.check_mesh_quality(fem, list(fem.BaseFEModel.MeshManager.GetMeshes()))

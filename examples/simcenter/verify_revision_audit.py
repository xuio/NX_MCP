def run(executor):
    import importlib
    import json
    from pathlib import Path

    import nx_mcp.simcenter.result_identity as identity
    from nx_mcp.workspace import Workspace

    importlib.reload(identity)
    import nx_mcp.simcenter.revisions as revisions

    importlib.reload(revisions)
    sim = executor.session.Parts.BaseWork
    if "C-transient-fine-20260908" not in sim.FullPath:
        raise ValueError("Requires isolated benchmark")
    fem = sim.FemPart
    parts = [sim, fem]
    links = {}
    for key in ["AssociatedCadPart", "IdealizedPart", "MasterCadPart"]:
        part = getattr(fem, key)
        links[key] = part.FullPath if part else None
        if part and not any(p.Tag == part.Tag for p in parts):
            parts.append(part)
    if len(parts) != 3:
        raise ValueError("Expected benchmark CAD/FEM/SIM dependency set")
    root = Path(sim.FullPath).parent
    job = json.loads((root / "fine-solve-01.json").read_text())
    expected = [
        {"path": str(root / row["name"]), "sha256": row["sha256"]} for row in job["model_files"]
    ]
    docs = [
        {"path": p.FullPath, "modified": bool(p.IsModified), "fully_loaded": bool(p.IsFullyLoaded)}
        for p in parts
    ]
    audit = revisions.audit_saved_revision(
        Workspace(r"D:\CAD\SIMCENTER_MCP_WORKSPACE"), expected, docs
    )
    return {
        "job_id": job["job_id"],
        "native_dependencies": docs,
        "associations": links,
        "audit": audit,
    }

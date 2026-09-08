"""Refine only the independent cloned duct FEM; preserve reference meshes/files."""


def run(executor):
    import hashlib
    import json
    import shutil
    from pathlib import Path

    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    session, nx = executor.session, executor.nxopen
    root = executor.workspace.resolve("ui-benchmarks")
    clone_folder = root / "D-independent-clone-native-20260908-r1"
    sim_folder = root / "D-independent-clone-export-20260908-r1"
    sim = session.Parts.BaseWork
    if executor.workspace.resolve(sim.FullPath) != sim_folder / "independent_export.sim":
        raise ValueError("Activate the independent export SIM")
    fem = sim.FemPart
    if executor.workspace.resolve(fem.FullPath) != clone_folder / "independent_mesh.fem":
        raise ValueError("SIM must reference only the independent FEM")
    if sim.IsModified or fem.IsModified or str(fem.PartUnits) != "1":
        raise ValueError("Require saved millimeter clone before refinement")

    def counts(part):
        elements, nodes = part.BaseFEModel.FeelementLabelMap, part.BaseFEModel.FenodeLabelMap
        try:
            return {"elements": elements.NumElements, "nodes": nodes.NumNodes}
        finally:
            elements.Dispose()
            nodes.Dispose()

    other_fems = [p for p in session.Parts if type(p).__name__ == "FemPart" and p != fem]
    before_other_meshes = {p.FullPath: counts(p) for p in other_fems}
    before_flags = {p.FullPath: bool(p.IsModified) for p in session.Parts if p not in (sim, fem)}
    original_folder = root / "D-cavity-documents-20260908-r2"
    protected = [
        original_folder / "benchmark_4ba7072a1d7a_mesh.fem",
        original_folder / "benchmark_4ba7072a1d7a_geometry.prt",
        root / "D-fine-k0-solve-20260908-r1/fine_k0_solve_r1.sim",
    ]
    hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    before_counts = counts(fem)
    if before_counts != {"elements": 186765, "nodes": 71748}:
        raise ValueError("Expected the unrefined independent copy")
    manager = fem.BaseFEModel.MeshManager
    meshes = list(manager.GetMeshes())
    cores = [m for m in meshes if m.Name == "3d_mesh(1)"]
    if len(meshes) != 2 or len(cores) != 1:
        raise ValueError("Expected one core and one boundary-layer mesh")
    record = clone_folder / "independent-refinement-r1.json"
    if record.exists():
        raise ValueError("Refinement already attempted; inspect its durable receipt")
    backup = clone_folder / "before-independent-refinement-r1"
    backup.mkdir(exist_ok=False)
    for part in (sim, fem):
        shutil.copy2(part.FullPath, backup / Path(part.FullPath).name)
    data = {
        "state": "accepted",
        "before_counts": before_counts,
        "requested_size_mm": 1.25,
        "solver_launched": False,
        "results_stale": True,
        "saved": False,
    }

    def persist():
        record.write_text(json.dumps(data, indent=2))

    persist()
    _, status = session.Parts.SetDisplay(fem, False, False)
    if status:
        status.Dispose()
    session.Parts.SetWork(fem)
    mark = session.SetUndoMark(
        nx.Session.MarkVisibility.Visible, "Refine independent duct core to 1.25 mm"
    )
    builder = None
    try:
        controls = list(fem.BaseFEModel.MeshControls)
        if len(controls) != 1:
            raise ValueError("Expected one layer control")
        control = fem.BaseFEModel.MeshControls.CreateBuilder(controls[0])
        try:
            layer = {
                "layers": control.NumberOfLayers,
                "growth_rate": control.GrowthRate,
                "first_layer_mm": float(control.FirstLayerThickness.GetFormula()),
                "face_count": len(control.Selection.GetArray()),
            }
        finally:
            control.Destroy()
        if layer != {"layers": 8, "growth_rate": 1.2, "first_layer_mm": 0.1, "face_count": 4}:
            raise ValueError("Unexpected layer parameters")
        data["layer_control"] = layer
        builder = manager.CreateMesh3dTetBuilder(cores[0])
        old, unit = builder.PropertyTable.GetBaseScalarWithDataPropertyValue(
            "quad mesh overall edge size"
        )
        if old != 1.5 or builder.ElementType.ElementTypeName != "Fluid Linear Tetrahedron":
            raise ValueError("Expected 1.5 mm fluid core")
        builder.AutoSizeOption = False
        builder.PropertyTable.SetBaseScalarWithDataPropertyValue(
            "quad mesh overall edge size", 1.25, unit
        )
        data["state"] = "meshing"
        persist()
        builder.CommitMesh()
        builder.Destroy()
        builder = None
        current = list(manager.GetMeshes())
        reader = manager.CreateMesh3dTetBuilder(next(m for m in current if m.Name == "3d_mesh(1)"))
        try:
            size, _ = reader.PropertyTable.GetBaseScalarWithDataPropertyValue(
                "quad mesh overall edge size"
            )
            if size != 1.25 or len(current) != 2:
                raise ValueError("Committed mesh differs from requested settings")
        finally:
            reader.Destroy()
        data["after_counts"] = counts(fem)
        if data["after_counts"]["elements"] <= before_counts["elements"]:
            raise ValueError("Refinement did not increase element count")
        data["actual_size_mm"] = size
        data["other_meshes_preserved"] = before_other_meshes == {
            p.FullPath: counts(p) for p in other_fems
        }
        data["other_flags_preserved"] = before_flags == {
            p.FullPath: bool(p.IsModified) for p in session.Parts if p not in (sim, fem)
        }
        data["source_files_preserved"] = all(
            hashlib.sha256(p.read_bytes()).hexdigest() == digest for p, digest in hashes.items()
        )
        assert (
            data["other_meshes_preserved"]
            and data["other_flags_preserved"]
            and data["source_files_preserved"]
        )
        executor.objects.invalidate_part(executor._part_id(fem))
        executor.objects.invalidate_part(executor._part_id(sim))
        data["state"] = "mesh_committed"
        persist()
        # After save starts, rollback cannot undo disk writes; retain backups and report partial errors.
        data["save_started"] = True
        persist()
        for part in (fem, sim):
            status = part.Save(
                nx.BasePart.SaveComponents.FalseValue, nx.BasePart.CloseAfterSave.FalseValue
            )
            try:
                assert not status.NumberUnsavedParts and not status.NumberUnsavedObjects
            finally:
                status.Dispose()
        data["saved"] = True
        data["state"] = "refined_and_saved"
        data["remaining_validation"] = [
            "SIM reopen and fresh deck export",
            "mesh quality",
            "refined solve",
            "numerical mesh sensitivity",
        ]
        fem.ModelingViews.WorkView.Fit()
    except Exception as error:
        if builder:
            builder.Destroy()
            builder = None
        data.update(
            state="failed",
            error=str(error),
            nx_code=getattr(error, "ErrorCode", None),
            mutation_outcome="partial",
        )
        if not data.get("save_started"):
            session.UndoToMark(mark, None)
            session.DeleteUndoMark(mark, None)
            data["rollback_counts"] = counts(fem)
            data["mutation_outcome"] = (
                "rolled_back" if data["rollback_counts"] == before_counts else "partial"
            )
        raise
    finally:
        try:
            if builder:
                builder.Destroy()
        finally:
            _, status = session.Parts.SetDisplay(sim, False, False)
            if status:
                status.Dispose()
            session.Parts.SetWork(sim)
            persist()
    return data

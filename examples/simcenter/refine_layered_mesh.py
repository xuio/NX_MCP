def run(executor):
    import hashlib
    import json
    import shutil
    import xml.etree.ElementTree as ET
    from pathlib import Path

    import NXOpen as nx
    import NXOpen.CAE as cae

    from nx_mcp.simcenter.properties import read_properties

    s = executor.session
    sim = s.Parts.BaseWork
    if type(sim).__name__ != "SimPart" or "D-cavity-documents-20260908-r2" not in sim.FullPath:
        raise ValueError("Isolated cavity SIM required")
    sim_path = sim.FullPath
    root = Path(sim_path).parent
    record = root / "fluid-layered-02.json"
    if record.exists():
        return {"replayed": True, "receipt": json.loads(record.read_text())}
    fem = sim.FemPart
    manager = fem.BaseFEModel.MeshManager
    meshes = list(manager.GetMeshes())
    if len(meshes) != 2:
        raise ValueError("Expected existing core and layer meshes")

    def boundaries(part):
        return [
            {
                "name": b.Name,
                "properties": read_properties(b.PropertyTable, nx),
                "target_count": len(b.TargetSetManager.GetTargetSetMembers(0)[1]),
            }
            for b in part.Simulation.SimulationObjects
        ]

    before_boundaries = boundaries(sim)
    data = {
        "state": "accepted",
        "saved": False,
        "before_boundaries": before_boundaries,
        "results_stale": True,
    }
    with record.open("x") as f:
        json.dump(data, f)

    def persist():
        record.write_text(json.dumps(data, indent=2))

    backup = root / "before-fluid-layered-02"
    backup.mkdir(exist_ok=False)
    for part in (sim, fem):
        shutil.copy2(part.FullPath, backup / Path(part.FullPath).name)
        st = part.Save(nx.BasePart.SaveComponents.FalseValue, nx.BasePart.CloseAfterSave.FalseValue)
        st.Dispose()
    _, st = s.Parts.SetDisplay(fem, False, False)
    if st:
        st.Dispose()
    s.Parts.SetWork(fem)
    mark = s.SetUndoMark(nx.Session.MarkVisibility.Visible, "Refine layered core mesh to 1.5 mm")
    builder = None
    try:
        controls = list(fem.BaseFEModel.MeshControls)
        if len(controls) != 1:
            raise ValueError("Expected one existing layer control")
        layer_reader = fem.BaseFEModel.MeshControls.CreateBuilder(controls[0])
        try:
            layer = {
                "layers": layer_reader.NumberOfLayers,
                "growth_rate": layer_reader.GrowthRate,
                "first_layer_mm": float(layer_reader.FirstLayerThickness.GetFormula()),
                "face_count": len(layer_reader.Selection.GetArray()),
            }
            if layer != {"layers": 8, "growth_rate": 1.2, "first_layer_mm": 0.1, "face_count": 4}:
                raise ValueError("Existing layer control differs")
        finally:
            layer_reader.Destroy()
        data["layer_control"] = layer
        meshes = [m for m in meshes if m.Name == "3d_mesh(1)"]
        if len(meshes) != 1:
            raise ValueError("Expected unique core mesh")
        builder = manager.CreateMesh3dTetBuilder(meshes[0])
        old_size, unit = builder.PropertyTable.GetBaseScalarWithDataPropertyValue(
            "quad mesh overall edge size"
        )
        if old_size != 2.0:
            raise ValueError("Expected baseline 2 mm mesh")
        builder.AutoSizeOption = False
        builder.PropertyTable.SetBaseScalarWithDataPropertyValue(
            "quad mesh overall edge size", 1.5, unit
        )
        builder.CommitMesh()
        builder.Destroy()
        builder = None
        current = list(manager.GetMeshes())
        if len(current) != 2:
            raise ValueError("Mesh count differs")
        reader = manager.CreateMesh3dTetBuilder(next(m for m in current if m.Name == "3d_mesh(1)"))
        try:
            value, u = reader.PropertyTable.GetBaseScalarWithDataPropertyValue(
                "quad mesh overall edge size"
            )
            if value != 1.5 or reader.ElementType.ElementTypeName != "Fluid Linear Tetrahedron":
                raise ValueError("Mesh readback differs")
        finally:
            reader.Destroy()
        e = fem.BaseFEModel.FeelementLabelMap
        n = fem.BaseFEModel.FenodeLabelMap
        try:
            data["counts"] = {"elements": e.NumElements, "nodes": n.NumNodes}
        finally:
            e.Dispose()
            n.Dispose()
        if data["counts"]["elements"] <= 97918:
            raise ValueError("Expected refinement")
        data["mesh_count"] = len(current)
        data["material_assignments"] = []
        for collector in manager.GetMeshCollectors():
            material_table = collector.ElementPropertyTable.GetNamedPropertyTablePropertyValue(
                "Fluid Property"
            )
            if material_table is None:
                raise ValueError("Missing fluid collector table")
            inherited, material = material_table.PropertyTable.GetMaterialPropertyValue("material")
            if material is None or inherited or material.Name != "Benchmark constant air":
                raise ValueError("Layered mesh air assignment changed")
            data["material_assignments"].append(
                {"collector": collector.Name, "material": material.Name}
            )
        data["state"] = "mesh_committed"
        persist()
        executor.objects.invalidate_part(executor._part_id(fem))
        executor.objects.invalidate_part(executor._part_id(sim))
        st = fem.Save(nx.BasePart.SaveComponents.FalseValue, nx.BasePart.CloseAfterSave.FalseValue)
        st.Dispose()
        data["saved"] = True
        persist()
        # Save this isolated SIM before closing; preserve any propagated boundary updates.
        st = sim.Save(nx.BasePart.SaveComponents.FalseValue, nx.BasePart.CloseAfterSave.FalseValue)
        st.Dispose()
        if sim.IsModified:
            raise ValueError("SIM remains modified; refuse close")
        sim.Close(
            nx.BasePart.CloseWholeTree.FalseValue, nx.BasePart.CloseModified.CloseModified, None
        )
        reopened, st = s.Parts.OpenBaseDisplay(sim_path)
        if st:
            st.Dispose()
        s.Parts.SetWork(reopened)
        s.ApplicationSwitchImmediate("UG_APP_SFEM")
        data["after_boundaries"] = boundaries(reopened)
        if data["before_boundaries"] != data["after_boundaries"]:
            raise ValueError("Boundary readback changed across remesh/reopen")
        reopened.Simulation.ActiveSolution.Solve(
            cae.SimSolutionSolveOption.WriteSolverInputFile,
            cae.SimSolutionSetupCheckOption.CompleteCheckAndOutputErrors,
        )
        deck = root / "benchmark_4ba7072a1d7a_analysis-Flow_benchmark.xml"
        raw = deck.read_bytes()
        xml = ET.fromstring(raw)
        data["export_counts"] = {
            "elements": len(xml.findall("./ElementList/Set/E")),
            "nodes": len(xml.find("NodeList")),
        }
        if data["export_counts"] != data["counts"]:
            raise ValueError("Exported mesh differs from FEM counts")
        data["layer_control_creation_readback"] = data.pop("layer_control")
        data["mesh_generated"] = True
        data["mesh_regeneration_required"] = False
        data["export_element_sets"] = [
            {"attributes": dict(e.attrib), "count": len(e)}
            for e in xml.findall("./ElementList/Set")
        ]
        data.update(
            state="verified",
            size_mm=1.5,
            deck_sha256=hashlib.sha256(raw).hexdigest(),
            solver_launched=False,
        )
    except Exception as exc:
        data.update(
            state="failed",
            error=str(exc),
            nx_code=getattr(exc, "ErrorCode", None),
            mutation_outcome="partial" if data["saved"] else "unknown",
        )
        if builder:
            builder.Destroy()
            builder = None
        if not data["saved"]:
            s.UndoToMark(mark, None)
            s.DeleteUndoMark(mark, None)
        raise
    finally:
        if builder:
            builder.Destroy()
        persist()
    return data

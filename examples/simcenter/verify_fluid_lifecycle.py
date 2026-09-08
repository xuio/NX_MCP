"""Save/reopen only the isolated three-document fluid cavity benchmark."""


def run(executor):
    import datetime
    import json
    import shutil
    from pathlib import Path

    import NXOpen.CAE as cae

    from nx_mcp.simcenter.fluid_domain import inspect_region_geometry
    from nx_mcp.simcenter.properties import read_properties

    s, nx = executor.session, executor.nxopen
    matches = [
        p
        for p in s.Parts
        if isinstance(p, cae.FemPart) and "D-cavity-documents-20260908-r2" in p.FullPath
    ]
    if len(matches) != 1:
        raise ValueError("Requires isolated cavity FEM")
    fem = matches[0]
    root = Path(fem.FullPath).parent
    record = root / "fluid-lifecycle-01.json"
    if record.exists():
        return {"replayed": True, "lifecycle": json.loads(record.read_text())}
    parts = {
        Path(p.FullPath).suffix: p
        for p in s.Parts
        if p.FullPath and Path(p.FullPath).parent == root
    }
    if set(parts) != {".prt", ".fem", ".sim"}:
        raise ValueError("Requires exactly CAD, FEM and SIM documents")
    if any(isinstance(p, cae.SimPart) and p.FemPart == fem and p != parts[".sim"] for p in s.Parts):
        raise ValueError("Another SIM references the benchmark FEM")
    paths = {ext: p.FullPath for ext, p in parts.items()}

    def snapshot(f):
        recipes = list(f.BaseFEModel.FluidDomains)
        if len(recipes) != 1:
            raise ValueError("Expected one region")
        em, nm = f.BaseFEModel.FeelementLabelMap, f.BaseFEModel.FenodeLabelMap
        try:
            counts = {"elements": em.NumElements, "nodes": nm.NumNodes}
        finally:
            em.Dispose()
            nm.Dispose()
        assignments = []
        for c in f.BaseFEModel.MeshManager.GetMeshCollectors():
            t = c.ElementPropertyTable.GetNamedPropertyTablePropertyValue(
                "Fluid Property"
            ).PropertyTable
            inherited, m = t.GetMaterialPropertyValue("material")
            if m is None:
                raise ValueError("Missing explicit air material")
            assignments.append(
                {
                    "collector": c.Name,
                    "inherited": inherited,
                    "material": m.Name,
                    "values": [
                        p
                        for p in read_properties(m.GetPropTable(), nx)
                        if p["name"]
                        in ["MassDensity", "DynamicVisc", "ThermalConductivity", "SpecificHeat"]
                    ],
                }
            )
        return {
            "geometry": inspect_region_geometry(f, list(recipes[0].GetFluidBodies())),
            "counts": counts,
            "assignments": assignments,
        }

    data = {
        "state": "accepted",
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "before": snapshot(fem),
        "paths": paths,
    }
    with record.open("x") as stream:
        json.dump(data, stream)

    def persist():
        temp = record.with_suffix(".tmp")
        temp.write_text(json.dumps(data, indent=2))
        temp.replace(record)

    try:
        backup = root / "before-fluid-lifecycle-01"
        backup.mkdir(exist_ok=False)
        for ext in [".prt", ".fem", ".sim"]:
            part = parts[ext]
            shutil.copy2(part.FullPath, backup / Path(part.FullPath).name)
            status = part.Save(
                nx.BasePart.SaveComponents.FalseValue, nx.BasePart.CloseAfterSave.FalseValue
            )
            if status:
                status.Dispose()
            if part.IsModified:
                raise ValueError("Document remains modified after save")
        data["state"] = "saved"
        persist()
        for ext in [".sim", ".fem", ".prt"]:
            if parts[ext].IsModified:
                raise ValueError("Document changed since save; refusing close")
            parts[ext].Close(
                nx.BasePart.CloseWholeTree.FalseValue, nx.BasePart.CloseModified.CloseModified, None
            )
        data["state"] = "closed"
        persist()
        reopened = {}
        for ext in [".prt", ".fem", ".sim"]:
            p, status = s.Parts.OpenBaseDisplay(paths[ext])
            if status:
                status.Dispose()
            reopened[ext] = p
        s.Parts.SetWork(reopened[".sim"])
        data["after"] = snapshot(reopened[".fem"])
        data["consistent"] = data["before"] == data["after"]
        data["state"] = "verified" if data["consistent"] else "mismatch"
        data["displayed_document"] = s.Parts.BaseDisplay.FullPath
        persist()
    except Exception as error:
        data.update(state="failed", error=str(error), nx_code=getattr(error, "ErrorCode", None))
        persist()
        raise
    return {"lifecycle": data}

"""Verify native SaveAs on an isolated SIM; explicitly report shared FEM ownership."""


def run(executor):
    import hashlib
    import json
    from pathlib import Path

    sim = executor.session.Parts.BaseWork
    if type(sim).__name__ != "SimPart" or "D-cavity-documents-20260908-r2" not in sim.FullPath:
        raise ValueError("Isolated duct SIM required")
    source = executor.workspace.ensure_inside(Path(sim.FullPath))
    target = executor.workspace.resolve("ui-benchmarks/F-sim-copy-20260908-r1/unique_job_copy.sim")
    if target.parent.exists():
        raise ValueError(
            "Fixture folder exists; inspect retained evidence instead of retrying SaveAs"
        )
    before_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    before_fem = sim.FemPart.FullPath
    before_name = sim.Simulation.ActiveSolution.Name
    old_part_id = executor._part_id(sim)
    target.parent.mkdir(parents=True)
    receipt = target.parent / "receipt.json"
    data = {
        "state": "accepted",
        "source_path": str(source),
        "target_path": str(target),
        "source_sha256_before": before_hash,
        "fem_before": before_fem,
        "solution_before": before_name,
        "source_live_modified_before": bool(sim.IsModified),
    }
    receipt.write_text(json.dumps(data, indent=2))
    try:
        status = sim.SaveAs(str(target))
        try:
            data["unsaved_parts"] = status.NumberUnsavedParts
            data["unsaved_objects"] = status.NumberUnsavedObjects
            if data["unsaved_parts"] or data["unsaved_objects"]:
                raise ValueError("Native SaveAs reported unsaved objects/parts")
        finally:
            status.Dispose()
        executor.objects.invalidate_part(old_part_id)
        data.update(
            target_exists=target.is_file(),
            target_bytes=target.stat().st_size,
            source_sha256_after=hashlib.sha256(source.read_bytes()).hexdigest(),
            current_object_path=sim.FullPath,
            work_path=executor.session.Parts.BaseWork.FullPath,
            display_path=executor.session.Parts.BaseDisplay.FullPath,
            fem_after=sim.FemPart.FullPath,
            solution_after=sim.Simulation.ActiveSolution.Name,
        )
        if data["source_sha256_after"] != before_hash:
            raise ValueError("Source file changed during SaveAs")
        if data["fem_after"] != before_fem or data["solution_after"] != before_name:
            raise ValueError("Unexpected FEM association or solution change")
        data.update(
            state="verified",
            shared_fem=True,
            independent_geometry_variant=False,
            scope="Native SIM copy only; FEM/CAD duplication and reassociation remain required",
        )
    except Exception as error:
        data.update(
            state="failed",
            error=str(error),
            nx_code=getattr(error, "ErrorCode", None),
            recovery="Inspect retained files and work/display state; no automatic file deletion",
        )
        raise
    finally:
        receipt.write_text(json.dumps(data, indent=2))
    return data

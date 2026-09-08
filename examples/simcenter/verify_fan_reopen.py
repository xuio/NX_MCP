"""Create an isolated flow SIM and verify native fan table persistence."""


def run(executor):
    import hashlib
    import importlib
    from pathlib import Path

    from nx_mcp.simcenter import fan_field

    importlib.reload(fan_field)
    session, nx = executor.session, executor.nxopen
    previous_work, previous_display = session.Parts.BaseWork, session.Parts.BaseDisplay
    original_flags = {part.FullPath: bool(part.IsModified) for part in session.Parts}
    manifest = {
        "name": "Retained synthetic fan",
        "pressure_convention": "static",
        "rpm": 1000,
        "reference_density_kg_m3": 1.2,
        "points": [
            {"flow_m3_s": 0, "pressure_Pa": 1},
            {"flow_m3_s": 0.0002, "pressure_Pa": 0.5},
            {"flow_m3_s": 0.0004, "pressure_Pa": 0},
        ],
        "stall_region": "Synthetic benchmark only",
        "provenance": {"kind": "assumed", "source": "Save/reopen → fixture " * 30},
        "scaling_rpm_range": [800, 1200],
        "scaling_validity": "Synthetic only",
    }
    try:
        executor._sim_create_benchmark(
            "ui-benchmarks/F-fan-reopen-20260908-r1", analysis_type="flow"
        )
        sim = session.Parts.BaseWork
        result = fan_field.create_fan_table(session, sim, manifest)
        result.pop("table")
        status = sim.Save(
            nx.BasePart.SaveComponents.FalseValue, nx.BasePart.CloseAfterSave.FalseValue
        )
        try:
            assert not status.NumberUnsavedParts and not status.NumberUnsavedObjects
        finally:
            status.Dispose()
        assert not sim.IsModified
        path = sim.FullPath
        digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        old_id = executor._part_id(sim)
        sim.Close(
            nx.BasePart.CloseWholeTree.FalseValue, nx.BasePart.CloseModified.CloseModified, None
        )
        executor.objects.invalidate_part(old_id)
        reopened, status = session.Parts.OpenBaseDisplay(path)
        if status:
            status.Dispose()
        session.Parts.SetWork(reopened)
        tables = [field for field in reopened.FieldManager.Fields if field.Name == manifest["name"]]
        assert len(tables) == 1
        table = tables[0]
        assert fan_field.read_manifest(table) == result["manifest"]
        independent, dependent = table.GetIndependentVariables(), table.GetDependentVariables()
        assert len(independent) == len(dependent) == 1
        units = reopened.UnitCollection
        q = [
            units.Convert(independent[0].Units, units.FindObject("CubicMeterPerSecond"), x)
            for x in table.GetData(independent[0])
        ]
        p = [
            units.Convert(dependent[0].Units, units.FindObject("PressurePascals"), x)
            for x in table.GetData(dependent[0])
        ]
        fan_field.verify_samples(result["readback"]["flow_m3_s"], q)
        fan_field.verify_samples(result["readback"]["pressure_Pa"], p)
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
        result.update(
            document_path=path,
            saved=True,
            save_reopen_tested=True,
            document_sha256=digest,
            reopened_flow_m3_s=q,
            reopened_pressure_Pa=p,
            reopened_modified=bool(reopened.IsModified),
            solver_launched=False,
        )
    finally:
        if previous_display is not None:
            _, status = session.Parts.SetDisplay(previous_display, False, False)
            if status:
                status.Dispose()
        if previous_work is not None:
            session.Parts.SetWork(previous_work)
    after = {
        part.FullPath: bool(part.IsModified)
        for part in session.Parts
        if part.FullPath in original_flags
    }
    assert after == original_flags
    result["original_document_flags_preserved"] = True
    result["previous_work_display_restored"] = (
        session.Parts.BaseWork == previous_work and session.Parts.BaseDisplay == previous_display
    )
    return result

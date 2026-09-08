def run(executor):
    import hashlib
    import importlib
    import json
    from pathlib import Path

    import NXOpen.CAE as cae

    from nx_mcp.simcenter import fan_field

    importlib.reload(fan_field)
    s = executor.session
    sim = s.Parts.BaseWork
    if type(sim).__name__ != "SimPart" or "D-cavity-documents-20260908-r2" not in sim.FullPath:
        raise ValueError("Cavity SIM required")
    root = Path(sim.FullPath).parent
    record = root / "fan-configuration-01.json"
    if record.exists():
        return {"replayed": True, "receipt": json.loads(record.read_text())}
    data = {
        "state": "accepted",
        "candidate_mode": 5,
        "purpose": "isolated synthetic fan solve; solver semantics pending",
        "solver_launched": False,
    }
    with record.open("x") as f:
        json.dump(data, f)
    mark = s.SetUndoMark(executor.nxopen.Session.MarkVisibility.Visible, "Probe fan mode export")
    inlet = next(b for b in sim.Simulation.SimulationObjects if b.Name == "Duct Inlet")
    props = inlet.PropertyTable
    old_mode = props.GetIntegerPropertyValue("Mode Option")
    old_field = props.GetScalarFieldWrapperPropertyValue("Fan Curve")
    try:
        manifest = {
            "name": "Synthetic mode probe",
            "pressure_convention": "static",
            "rpm": 1000,
            "reference_density_kg_m3": 1.2,
            "points": [
                {"flow_m3_s": 0, "pressure_Pa": 1},
                {"flow_m3_s": 0.0002, "pressure_Pa": 0.5},
                {"flow_m3_s": 0.0004, "pressure_Pa": 0},
            ],
            "stall_region": "Not modeled; synthetic only",
            "provenance": {"kind": "assumed", "source": "Mode discovery benchmark"},
        }
        table = fan_field.create_fan_table(s, sim, manifest)["table"]
        wrapper = sim.FieldManager.CreateScalarFieldWrapperWithField(table, 1.0)
        props.SetScalarFieldWrapperPropertyValue("Fan Curve", wrapper)
        props.SetIntegerPropertyValue("Mode Option", 5)
        props.SetIntegerPropertyValue("Pressure", 1)
        props.SetBaseScalarWithDataPropertyValue(
            "Pressure Value", 101325.0, sim.UnitCollection.FindObject("PressurePascals")
        )
        data["readback_mode"] = props.GetIntegerPropertyValue("Mode Option")
        value, unit = props.GetBaseScalarWithDataPropertyValue("Pressure Value")
        data["inlet_pressure"] = {
            "value": value,
            "units": unit.Name,
            "mode": props.GetIntegerPropertyValue("Pressure"),
        }
        if value != 101325.0 or unit.Name != "PressurePascals":
            raise ValueError("Pressure readback differs")
        # Preserve existing generated input before testing the current in-memory model.
        backups = {
            p: p.read_bytes()
            for p in root.glob("benchmark_4ba7072a1d7a_analysis-Flow_benchmark.*")
            if p.suffix in (".xml", ".map")
        }
        for p, blob in backups.items():
            target = root / ("pre-fan-mode-probe-02" + p.suffix)
            if not target.exists():
                target.write_bytes(blob)
        sim.Simulation.ActiveSolution.Solve(
            cae.SimSolutionSolveOption.WriteSolverInputFile,
            cae.SimSolutionSetupCheckOption.CompleteCheckAndOutputErrors,
        )
        data["state"] = "export_returned"
        for p in root.glob("benchmark_4ba7072a1d7a_analysis-Flow_benchmark.xml"):
            target = root / "fan-mode-probe-02.xml"
            target.write_bytes(p.read_bytes())
            data["export"] = {
                "path": str(target),
                "size": target.stat().st_size,
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            }
    except Exception as exc:
        data.update(state="failed", error=str(exc), nx_code=getattr(exc, "ErrorCode", None))
        raise
    finally:
        if data["state"] != "export_returned":
            s.UndoToMark(mark, None)
            s.DeleteUndoMark(mark, None)
            data["rollback_verified"] = (
                props.GetIntegerPropertyValue("Mode Option") == old_mode
                and props.GetScalarFieldWrapperPropertyValue("Fan Curve") == old_field
            )
        else:
            import NXOpen as nx

            status = sim.Save(
                nx.BasePart.SaveComponents.FalseValue, nx.BasePart.CloseAfterSave.FalseValue
            )
            status.Dispose()
            data["manifest"] = manifest
            data["saved"] = True
        record.write_text(json.dumps(data, indent=2))
    return data

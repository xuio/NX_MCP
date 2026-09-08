def run(executor):
    import hashlib
    import json
    import xml.etree.ElementTree as ET
    from pathlib import Path

    import NXOpen as nx
    import NXOpen.CAE as cae

    from nx_mcp.simcenter.properties import read_properties

    s = executor.session
    sim = s.Parts.BaseWork
    if type(sim).__name__ != "SimPart" or "D-cavity-documents-20260908-r2" not in sim.FullPath:
        raise ValueError("Isolated cavity required")
    root = Path(sim.FullPath).parent
    record = root / "head-loss-config-02.json"
    if record.exists():
        return {"replayed": True, "receipt": json.loads(record.read_text())}
    opening = next(b for b in sim.Simulation.SimulationObjects if b.Name == "Duct Opening")
    if opening.PropertyTable.GetNamedPropertyTablePropertyValue("Head Loss") is not None:
        raise ValueError("Opening already has a loss table")
    before = {int(t.Tag) for t in sim.ModelingObjectPropertyTables}
    mark = s.SetUndoMark(nx.Session.MarkVisibility.Visible, "Synthetic duct restriction K=2")
    data = {
        "state": "accepted",
        "coefficient": 2.0,
        "coefficient_convention": "solver_verification_pending",
        "solver_launched": False,
    }
    with record.open("x") as f:
        json.dump(data, f)
    try:
        table = sim.ModelingObjectPropertyTables.CreateModelingObjectPropertyTable(
            "Head Loss",
            "NX MULTIPHYSICS - Flow",
            "NX MULTIPHYSICS",
            "Synthetic outlet restriction K2",
            0,
        )
        table.PropertyTable.SetBaseScalarWithDataPropertyValue(
            "Head Loss Coefficient",
            2.0,
            table.PropertyTable.GetBaseScalarWithDataPropertyValue("Head Loss Coefficient")[1],
        )
        opening.PropertyTable.SetNamedPropertyTablePropertyValue("Head Loss", table)
        if opening.PropertyTable.GetNamedPropertyTablePropertyValue("Head Loss") != table:
            raise ValueError("Head loss association mismatch")
        data["readback"] = read_properties(table.PropertyTable, nx)
        coeff = next(p for p in data["readback"] if p["name"] == "Head Loss Coefficient")
        if coeff["value"] != 2.0:
            raise ValueError("Coefficient readback differs")
        st = sim.Save(nx.BasePart.SaveComponents.FalseValue, nx.BasePart.CloseAfterSave.FalseValue)
        st.Dispose()
        data["saved"] = True
        sim.Simulation.ActiveSolution.Solve(
            cae.SimSolutionSolveOption.WriteSolverInputFile,
            cae.SimSolutionSetupCheckOption.CompleteCheckAndOutputErrors,
        )
        deck = root / "benchmark_4ba7072a1d7a_analysis-Flow_benchmark.xml"
        raw = deck.read_bytes()
        xml = ET.fromstring(raw)
        data["export_head_loss"] = [
            ET.tostring(e, encoding="unicode")
            for e in xml.iter()
            if e.get("name") == "Head Loss Coefficient"
        ]
        data.update(state="export_returned", deck_sha256=hashlib.sha256(raw).hexdigest())
    except Exception as exc:
        data.update(state="failed", error=str(exc), nx_code=getattr(exc, "ErrorCode", None))
        s.UndoToMark(mark, None)
        s.DeleteUndoMark(mark, None)
        data["rollback_verified"] = {
            int(t.Tag) for t in sim.ModelingObjectPropertyTables
        } == before and opening.PropertyTable.GetNamedPropertyTablePropertyValue(
            "Head Loss"
        ) is None
        data["disk_state_may_differ"] = data.get("saved", False)
        raise
    finally:
        record.write_text(json.dumps(data, indent=2))
    return data

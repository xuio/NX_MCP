def run(executor):
    import hashlib
    import json
    import xml.etree.ElementTree as ET
    from pathlib import Path

    import NXOpen as nx
    import NXOpen.CAE as cae

    s = executor.session
    sim = s.Parts.BaseWork
    if type(sim).__name__ != "SimPart" or "D-cavity-documents-20260908-r2" not in sim.FullPath:
        raise ValueError("Isolated cavity SIM required")
    root = Path(sim.FullPath).parent
    record = root / "fan-reference-pressure-01.json"
    if record.exists():
        return {"replayed": True, "receipt": json.loads(record.read_text())}
    table = sim.Simulation.ActiveSolution.PropertyTable
    before = table.GetScalarFieldWrapperPropertyValue("Absolute Pressure")
    data = {"state": "accepted", "requested_pressure_Pa": 101325.0, "solver_launched": False}
    with record.open("x") as f:
        json.dump(data, f)
    mark = s.SetUndoMark(nx.Session.MarkVisibility.Visible, "Equalize fan ambient pressure")
    try:
        expr = sim.Expressions.CreateSystemNumberExpression(
            "101325.0", sim.UnitCollection.FindObject("PressurePascals")
        )
        wrapper = sim.FieldManager.CreateScalarFieldWrapperWithExpression(expr)
        table.SetScalarFieldWrapperPropertyValue("Absolute Pressure", wrapper)
        actual = table.GetScalarFieldWrapperPropertyValue("Absolute Pressure").GetExpression()
        if float(actual.GetFormula()) != 101325.0 or actual.Units.Name != "PressurePascals":
            raise ValueError("Ambient pressure readback mismatch")
        st = sim.Save(nx.BasePart.SaveComponents.FalseValue, nx.BasePart.CloseAfterSave.FalseValue)
        st.Dispose()
        data["saved"] = True
        sim.Simulation.ActiveSolution.Solve(
            cae.SimSolutionSolveOption.WriteSolverInputFile,
            cae.SimSolutionSetupCheckOption.CompleteCheckAndOutputErrors,
        )
        deck = root / "benchmark_4ba7072a1d7a_analysis-Flow_benchmark.xml"
        raw = deck.read_bytes()
        tree = ET.fromstring(raw)
        values = [
            float(p.findtext("Value"))
            for p in tree.iter("Property")
            if p.get("name") == "Absolute Pressure"
        ]
        if values != [101.325]:
            raise ValueError("Exported ambient pressure mismatch: " + str(values))
        data.update(
            state="export_verified",
            pressure_export=values,
            deck_sha256=hashlib.sha256(raw).hexdigest(),
        )
    except Exception as exc:
        data.update(state="failed", error=str(exc), nx_code=getattr(exc, "ErrorCode", None))
        s.UndoToMark(mark, None)
        s.DeleteUndoMark(mark, None)
        data["rollback_verified"] = (
            table.GetScalarFieldWrapperPropertyValue("Absolute Pressure") == before
        )
        data["disk_state_may_differ"] = data.get("saved", False)
        raise
    finally:
        record.write_text(json.dumps(data, indent=2))
    return data

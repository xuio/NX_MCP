"""Launch one recorded, bounded native CFD precursor run; never retry on timeout."""


def run(executor):
    import datetime
    import hashlib
    import json
    import xml.etree.ElementTree as ET
    from pathlib import Path

    import NXOpen.CAE as cae

    from nx_mcp.runtime import NXToolError

    sim = executor.session.Parts.BaseWork
    if type(sim).__name__ != "SimPart" or "D-cavity-documents-20260908-r2" not in sim.FullPath:
        raise ValueError("Cavity SIM required")
    root = Path(sim.FullPath).parent
    record = root / "cavity-fan-solve-06.json"
    if record.exists():
        return {"replayed": True, "job": json.loads(record.read_text())}
    deck = root / "benchmark_4ba7072a1d7a_analysis-Flow_benchmark.xml"
    raw = deck.read_bytes()
    xml = ET.fromstring(raw)
    if [
        p.findtext("Value", "").strip()
        for p in xml.iter("Property")
        if p.get("name") == "Turbulence Model"
    ] != ["0"]:
        raise ValueError("Expected changed flow-model selector in fresh input")
    if [
        p.findtext("Value", "").strip()
        for p in xml.iter("Property")
        if p.get("name") == "Wall Treatment"
    ] != ["0"]:
        raise ValueError("Expected explicit wall selector")
    if xml.get("class") != "Flow":
        raise ValueError("Expected Flow input")
    limits = [
        float(p.findtext("Value"))
        for p in xml.iter("Property")
        if p.get("name") == "3D Flow Steady State - Iteration Limit"
    ]
    if limits != [1000.0]:
        raise ValueError("Unexpected iteration budget")
    opening = next(e for e in xml.iter("FlowBc") if e.get("type") == "Opening")
    pv = {p.get("name"): (p.findtext("Value") or "").strip() for p in opening.findall("Property")}
    if pv["Pressure"] != "1" or abs(float(pv["Pressure Value"]) - 101.325) > 1e-7:
        raise ValueError("Opening export mismatch")
    inlet = next(e for e in xml.iter("FlowBc") if e.get("type") == "Inlet")
    ip = {p.get("name"): p for p in inlet.findall("Property")}
    if ip["Mode Option"].findtext("Value").strip() != "5":
        raise ValueError("Expected candidate fan mode")
    if (
        ip["Pressure"].findtext("Value").strip() != "1"
        or abs(float(ip["Pressure Value"].findtext("Value")) - 101.325) > 1e-7
    ):
        raise ValueError("Expected equal ambient inlet pressure")
    rows = [[float(x) for x in row.text.split()] for row in ip["Fan Curve"].findall("_")]
    if rows != [[0.0, 0.001], [200000.0, 0.0005], [400000.0, 0.0]]:
        raise ValueError("Fan table export differs")
    native = next(b for b in sim.Simulation.SimulationObjects if b.Name == "Duct Inlet")
    if native.PropertyTable.GetIntegerPropertyValue("Mode Option") != 5:
        raise ValueError("Current model differs from candidate fan deck")
    references = [
        float(p.findtext("Value"))
        for p in xml.iter("Property")
        if p.get("name") == "Absolute Pressure"
    ]
    if references != [101.325]:
        raise ValueError("Expected equalized pressure reference")
    coefficients = [
        float(p.findtext("Value"))
        for p in xml.iter("Property")
        if p.get("name") == "Head Loss Coefficient"
    ]
    if coefficients != [2.0]:
        raise ValueError("Expected K=2 restriction in fresh export")
    native_opening = next(b for b in sim.Simulation.SimulationObjects if b.Name == "Duct Opening")
    loss = native_opening.PropertyTable.GetNamedPropertyTablePropertyValue("Head Loss")
    if (
        loss is None
        or loss.PropertyTable.GetBaseScalarWithDataPropertyValue("Head Loss Coefficient")[0] != 2.0
    ):
        raise ValueError("Native opening restriction mismatch")
    mesh_counts = {
        "elements": len(xml.findall("./ElementList/Set/E")),
        "nodes": len(xml.findall("./NodeList/N")),
    }
    if mesh_counts != {"elements": 97918, "nodes": 39306}:
        raise ValueError("Expected verified refined mesh")
    fem = sim.FemPart
    em, nm = fem.BaseFEModel.FeelementLabelMap, fem.BaseFEModel.FenodeLabelMap
    try:
        if em.NumElements != mesh_counts["elements"] or nm.NumNodes != mesh_counts["nodes"]:
            raise ValueError("Current FEM differs from exported mesh")
    finally:
        em.Dispose()
        nm.Dispose()
    sets = {e.get("elementType"): len(e) for e in xml.findall("./ElementList/Set")}
    if sets != {"TET4 Fluid": 36222, "WEDGE6 Fluid": 61696}:
        raise ValueError("Layered element sets differ")
    data = {
        "element_sets": sets,
        "mesh_counts": mesh_counts,
        "mesh_size_mm": 2.0,
        "job_id": "cavity-fan-solve-06",
        "state": "accepted",
        "deck_sha256": hashlib.sha256(raw).hexdigest(),
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "iteration_limit": 1000,
        "solver_launched": "not_yet_confirmed",
        "numerical_validation": "not_performed",
        "scope": "synthetic fan mode-5 verification; no thermal load; not acceptance D",
    }
    with record.open("x") as stream:
        json.dump(data, stream)

    def persist():
        tmp = record.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(record)

    sol = sim.Simulation.ActiveSolution
    old = sol.PropertyTable.GetBooleanPropertyValue("Foreground")
    try:
        sol.PropertyTable.SetBooleanPropertyValue("Foreground", False)
        data["state"] = "launch_requested"
        persist()
        sol.Solve(
            cae.SimSolutionSolveOption.Solve,
            cae.SimSolutionSetupCheckOption.CompleteCheckAndOutputErrors,
        )
        data["state"] = "launch_api_returned"
    except Exception as exc:
        data.update(state="api_failed", error=str(exc), nx_code=getattr(exc, "ErrorCode", None))
        raise NXToolError(
            "NX_SIM_SOLVE_FAILED", "Native flow solve launch failed", details={"job": data}
        ) from exc
    finally:
        try:
            sol.PropertyTable.SetBooleanPropertyValue("Foreground", old)
        finally:
            persist()
    return {"job": data}

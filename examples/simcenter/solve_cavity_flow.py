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
    record = root / "cavity-flow-solve-01.json"
    if record.exists():
        return {"replayed": True, "job": json.loads(record.read_text())}
    deck = root / "benchmark_4ba7072a1d7a_analysis-Flow_benchmark.xml"
    raw = deck.read_bytes()
    xml = ET.fromstring(raw)
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
    data = {
        "job_id": "cavity-flow-solve-01",
        "state": "accepted",
        "deck_sha256": hashlib.sha256(raw).hexdigest(),
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "iteration_limit": 1000,
        "solver_launched": "not_yet_confirmed",
        "numerical_validation": "not_performed",
        "scope": "constant-density duct precursor; no fan or thermal load",
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

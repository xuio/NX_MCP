"""Launch one recorded, bounded native CFD precursor run; never retry on timeout."""


def run(executor):
    import datetime
    import hashlib
    import xml.etree.ElementTree as ET
    from pathlib import Path

    import NXOpen.CAE as cae

    sim = executor.session.Parts.BaseWork
    if type(sim).__name__ != "SimPart" or "D-cavity-documents-20260908-r2" not in sim.FullPath:
        raise ValueError("Cavity SIM required")
    root = Path(sim.FullPath).parent
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
    for key, value in {
        "Maximum Residuals": 1e-6,
        "Global Flow Imbalance Fraction": 0.001,
        "Global Flow Imbalance Fraction Option": 1,
    }.items():
        actual = [float(p.findtext("Value")) for p in xml.iter("Property") if p.get("name") == key]
        if actual != [value]:
            raise ValueError("Tighter convergence export mismatch: " + key)
    controls = sim.Simulation.ActiveSolution.PropertyTable.GetNamedPropertyTablePropertyValue(
        "Flow Solution Parameters"
    ).PropertyTable
    if (
        controls.GetBaseScalarWithDataPropertyValue("Maximum Residuals")[0] != 1e-6
        or controls.GetBaseScalarWithDataPropertyValue("Global Flow Imbalance Fraction")[0] != 0.001
        or not controls.GetBooleanPropertyValue("Global Flow Imbalance Fraction Option")
    ):
        raise ValueError("Native convergence controls differ from export")
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
    if mesh_counts != {"elements": 186765, "nodes": 71748}:
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
    if sets != {"TET4 Fluid": 77133, "WEDGE6 Fluid": 109632}:
        raise ValueError("Layered element sets differ")
    checker = fem.ModelCheckMgr.CreateElementQualityCheckBuilder()
    checks = None
    try:
        checker.SelectionList.Add(list(fem.BaseFEModel.MeshManager.GetMeshes()))
        checks = checker.ExecuteCheck()
        quality = {
            "element_count": checks.ElementTestCount,
            "errors": sum(t.ErrorCount for t in checks.GetTestSummary()),
            "warnings": sum(t.WarnedCount for t in checks.GetTestSummary()),
        }
        if quality["element_count"] != 186765 or quality["errors"]:
            raise ValueError("Native mesh quality preflight failed: " + str(quality))
    finally:
        if checks is not None:
            checks.Dispose()
        checker.Destroy()
    data = {
        "convergence": {
            "rms_residual": 1e-6,
            "flow_imbalance_fraction": 0.001,
            "flow_imbalance_enabled": True,
        },
        "quality_preflight": quality,
        "element_sets": sets,
        "mesh_counts": mesh_counts,
        "mesh_size_mm": 1.5,
        "job_id": "cavity-fan-solve-09",
        "state": "accepted",
        "deck_sha256": hashlib.sha256(raw).hexdigest(),
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "iteration_limit": 1000,
        "solver_launched": "not_yet_confirmed",
        "numerical_validation": "not_performed",
        "scope": "synthetic fan mode-5 verification; no thermal load; not acceptance D",
    }
    import importlib

    import nx_mcp.simcenter.jobs as jobs_module

    importlib.reload(jobs_module)

    from nx_mcp.simcenter.jobs import JobStore
    from nx_mcp.simcenter.launch import launch_once
    from nx_mcp.simcenter.solver_manifest import input_identity, preserve_input

    store = JobStore(executor.workspace, "ui-benchmarks/D-cavity-documents-20260908-r2/jobs")
    manifest = {
        key: value
        for key, value in data.items()
        if key
        not in ("created_at", "state", "solver_launched", "deck_sha256", "numerical_validation")
    }
    manifest["input_xml_content_sha256"] = input_identity(raw)["xml_content_sha256"]
    manifest["analysis_path"] = sim.FullPath

    def native_launch():
        preserve_input(
            executor.workspace.ensure_inside(store.root / "cavity-fan-solve-09"),
            "before-launch",
            raw,
        )
        sol = sim.Simulation.ActiveSolution
        old = sol.PropertyTable.GetBooleanPropertyValue("Foreground")
        try:
            sol.PropertyTable.SetBooleanPropertyValue("Foreground", False)
            if sol.PropertyTable.GetBooleanPropertyValue("Foreground"):
                raise ValueError("Background solve setting did not commit")
            sol.Solve(
                cae.SimSolutionSolveOption.Solve,
                cae.SimSolutionSetupCheckOption.CompleteCheckAndOutputErrors,
            )
        finally:
            sol.PropertyTable.SetBooleanPropertyValue("Foreground", old)
        return {
            "background_launch_requested": True,
            "foreground_setting_restored": sol.PropertyTable.GetBooleanPropertyValue("Foreground")
            == old,
        }

    return {
        "job": launch_once(store, "cavity-fan-solve-09", manifest, native_launch),
        "scope": "actual native asynchronous launch with durable intent; process/result audit remains separate",
    }

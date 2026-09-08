def run(executor):
    import hashlib
    import json
    import xml.etree.ElementTree as ET
    from pathlib import Path

    s = executor.session
    sim = s.Parts.BaseWork
    if type(sim).__name__ != "SimPart" or "D-cavity-documents-20260908-r2" not in sim.FullPath:
        raise ValueError("Isolated cavity SIM required")
    root = Path(sim.FullPath).parent
    receipt = json.loads((root / "fluid-refinement-01.json").read_text())
    if receipt["before_boundaries"] != receipt["after_boundaries"]:
        raise ValueError("Boundary snapshot differs")
    fem = sim.FemPart
    e = fem.BaseFEModel.FeelementLabelMap
    n = fem.BaseFEModel.FenodeLabelMap
    try:
        counts = {"elements": e.NumElements, "nodes": n.NumNodes}
    finally:
        e.Dispose()
        n.Dispose()
    raw = (root / "benchmark_4ba7072a1d7a_analysis-Flow_benchmark.xml").read_bytes()
    xml = ET.fromstring(raw)
    exported = {
        "elements": len(xml.findall("./ElementList/Set/E")),
        "nodes": len(xml.findall("./NodeList/N")),
    }
    if counts != exported or counts != {"elements": 13397, "nodes": 3200}:
        raise ValueError("Native/exported refinement counts differ")
    return {
        "state": "verified",
        "counts": counts,
        "export_counts": exported,
        "boundary_readback_preserved": True,
        "deck_sha256": hashlib.sha256(raw).hexdigest(),
        "solver_launched": False,
        "prior_results_stale": True,
        "previous_failure": "ElementList groups counted instead of nested E elements",
    }

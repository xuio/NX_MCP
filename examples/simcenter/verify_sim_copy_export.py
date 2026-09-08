"""Verify distinct native export output for the SIM-copy fixture; never solve."""


def run(executor):
    import hashlib
    import xml.etree.ElementTree as ET
    from pathlib import Path

    import NXOpen.CAE as cae

    sim = executor.session.Parts.BaseWork
    if type(sim).__name__ != "SimPart" or not sim.FullPath.endswith(
        r"F-sim-copy-20260908-r1\unique_job_copy.sim"
    ):
        raise ValueError("Activate the isolated SIM copy first")
    root = executor.workspace.ensure_inside(Path(sim.FullPath).parent)
    original = executor.workspace.resolve("ui-benchmarks/D-cavity-documents-20260908-r2")
    source_files = [
        original / "benchmark_4ba7072a1d7a_analysis.sim",
        original / "benchmark_4ba7072a1d7a_analysis-Flow_benchmark.xml",
        original / "benchmark_4ba7072a1d7a_analysis-Flow_benchmark.bun",
    ]
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}
    target = executor.workspace.ensure_inside(root / "unique_job_copy-Flow_benchmark.xml")
    if target.exists():
        raise ValueError("Copy export already exists; inspect it before repeating")
    solution = sim.Simulation.ActiveSolution
    solution.Solve(
        cae.SimSolutionSolveOption.WriteSolverInputFile,
        cae.SimSolutionSetupCheckOption.CompleteCheckAndOutputErrors,
    )
    raw = target.read_bytes()
    xml = ET.fromstring(raw)
    counts = {
        "elements": len(xml.findall("./ElementList/Set/E")),
        "nodes": len(xml.findall("./NodeList/N")),
    }
    if counts != {"elements": 186765, "nodes": 71748}:
        raise ValueError("Copied SIM exports different mesh counts")
    after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}
    if before != after:
        raise ValueError("Original analysis or result files changed during copy export")
    associations = []
    for i in range(solution.ResultReferenceCount):
        directory, name = solution.GetResultReferenceByIndex(i).GetResultFile()
        associations.append({"directory": directory, "name": name, "freshness": "not_verified"})
    return {
        "export_path": str(target),
        "export_bytes": len(raw),
        "export_sha256": hashlib.sha256(raw).hexdigest(),
        "mesh_counts": counts,
        "original_files_unchanged": before == after,
        "original_hashes": after,
        "result_associations": associations,
        "solver_launched": False,
        "shared_fem": sim.FemPart.FullPath,
        "scope": "Distinct export from SIM copy; not independent FEM geometry or solved variant",
    }

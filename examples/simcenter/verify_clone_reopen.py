"""Open the disposable clone and check actual SIM/FEM/CAD associations."""


def run(executor):
    import hashlib

    from nx_mcp.simcenter.dependencies import inspect_direct
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    root = executor.workspace.resolve("ui-benchmarks")
    destination = root / "D-independent-clone-native-20260908-r1"
    expected = {
        destination / name
        for name in ("independent_flow.sim", "independent_mesh.fem", "independent_geometry.prt")
    }
    source = root / "D-fine-k0-solve-20260908-r1/fine_k0_solve_r1.sim"
    base = root / "D-cavity-documents-20260908-r2"
    originals = [
        source,
        base / "benchmark_4ba7072a1d7a_mesh.fem",
        base / "benchmark_4ba7072a1d7a_geometry.prt",
    ]
    hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in originals}
    before = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    opened = executor._sim_open(str(destination / "independent_flow.sim"))
    sim = executor.session.Parts.BaseWork
    dependencies = inspect_direct(executor.session, sim, executor.workspace)
    initial_unresolved = dependencies["unresolved"]
    cad_path = destination / "independent_geometry.prt"
    for issue in initial_unresolved:
        if (
            issue["association"] != "AssociatedCadPart"
            or executor.workspace.resolve(issue["path"]) != cad_path
        ):
            raise ValueError("Unexpected unresolved dependency; no automatic loading")
    if initial_unresolved:
        cad, status = executor.session.Parts.OpenBase(str(cad_path))
        try:
            assert not status or status.NumberUnloadedParts == 0
            assert executor.workspace.resolve(cad.FullPath) == cad_path
        finally:
            if status:
                status.Dispose()
        dependencies = inspect_direct(executor.session, sim, executor.workspace)
    actual = {executor.workspace.resolve(row["path"]) for row in dependencies["rows"]}
    assert actual == expected and not dependencies["unresolved"], dependencies["unresolved"]
    fem = sim.FemPart
    elements = fem.BaseFEModel.FeelementLabelMap
    nodes = fem.BaseFEModel.FenodeLabelMap
    try:
        counts = {"elements": elements.NumElements, "nodes": nodes.NumNodes}
    finally:
        elements.Dispose()
        nodes.Dispose()
    assert counts == {"elements": 186765, "nodes": 71748}, counts
    solution = sim.Simulation.ActiveSolution
    assert solution.AnalysisType == "Flow"
    opening = next(b for b in sim.Simulation.SimulationObjects if b.Name == "Duct Opening")
    table = opening.PropertyTable.GetNamedPropertyTablePropertyValue("Head Loss").PropertyTable
    coefficient, _ = table.GetBaseScalarWithDataPropertyValue("Head Loss Coefficient")
    assert coefficient == 0
    after = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    assert all(after.get(path) == flag for path, flag in before.items())
    assert all(hashlib.sha256(p.read_bytes()).hexdigest() == digest for p, digest in hashes.items())
    return {
        "state": "direct_dependency_rebinding_verified",
        "document": opened["document"],
        "dependencies": [
            {k: v for k, v in row.items() if k != "part"} for row in dependencies["rows"]
        ],
        "associations": dependencies["associations"],
        "initial_unresolved": initial_unresolved,
        "mesh_counts": counts,
        "solution": {
            "name": solution.Name,
            "solver": solution.SolverType,
            "analysis": solution.AnalysisType,
        },
        "head_loss_coefficient": coefficient,
        "source_files_preserved": True,
        "existing_document_flags_preserved": True,
        "solver_launched": False,
        "result_freshness": "not_verified",
        "remaining_checks": [
            "fan and selection equivalence",
            "mesh edit independence",
            "complete package dependencies",
        ],
    }

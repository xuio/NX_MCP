"""Export the disposable clone once and compare it with the saved reference deck."""


def run(executor):
    import hashlib
    import json
    import xml.etree.ElementTree as ET

    import NXOpen.CAE as cae

    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    root = executor.workspace.resolve("ui-benchmarks")
    folder = root / "D-independent-clone-native-20260908-r1"
    sim = executor.session.Parts.BaseWork
    if executor.workspace.resolve(sim.FullPath) != folder / "independent_flow.sim":
        raise ValueError("Activate the isolated independent clone")
    source_folder = root / "D-fine-k0-solve-20260908-r1"
    source_deck = source_folder / "fine_k0_solve_r1-Flow_benchmark.xml"
    source_fem_folder = root / "D-cavity-documents-20260908-r2"
    protected = [
        source_deck,
        source_folder / "fine_k0_solve_r1.sim",
        source_fem_folder / "benchmark_4ba7072a1d7a_mesh.fem",
        source_fem_folder / "benchmark_4ba7072a1d7a_geometry.prt",
    ]
    protected += [p for p in folder.iterdir() if p.is_file()]
    hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    flags = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    export_folder = root / "D-independent-clone-export-20260908-r1"
    if export_folder.exists():
        raise ValueError("Export folder exists; inspect retained files instead of replaying")
    previous_path = sim.FullPath
    copy_receipt = executor._sim_save_as(
        executor._reference(sim, "part", sim, "part")["id"],
        str(export_folder / "independent_export.sim"),
    )
    assert executor.workspace.resolve(sim.FemPart.FullPath) == folder / "independent_mesh.fem"
    deck = export_folder / "independent_export-Flow_benchmark.xml"
    intent = export_folder / "clone-export-intent.json"
    with intent.open("x") as stream:
        json.dump({"state": "accepted", "solver_launched": False, "document": sim.FullPath}, stream)
    solution = sim.Simulation.ActiveSolution
    solution.Solve(
        cae.SimSolutionSolveOption.WriteSolverInputFile,
        cae.SimSolutionSetupCheckOption.CompleteCheckAndOutputErrors,
    )

    def inspect(path):
        if path.stat().st_size > 64 * 1024 * 1024:
            raise ValueError("Deck exceeds bounded comparison size")
        raw = path.read_bytes()
        xml = ET.fromstring(raw)
        children = {}
        for child in xml:
            children.setdefault(child.tag, []).append(
                hashlib.sha256(ET.tostring(child)).hexdigest()
            )
        props = {}
        for prop in xml.iter("Property"):
            props.setdefault(prop.get("name"), []).append(ET.tostring(prop, encoding="unicode"))
        return {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "children": children,
            "properties": props,
        }

    reference, copied = inspect(source_deck), inspect(deck)
    prop_names = set(reference["properties"]) | set(copied["properties"])
    differences = {
        name: {
            "reference": reference["properties"].get(name),
            "clone": copied["properties"].get(name),
        }
        for name in prop_names
        if reference["properties"].get(name) != copied["properties"].get(name)
    }
    child_names = set(reference["children"]) | set(copied["children"])
    result = {
        "state": "comparison_returned",
        "source_deck": str(source_deck),
        "clone_deck": str(deck),
        "source_sha256": reference["sha256"],
        "clone_sha256": copied["sha256"],
        "different_sections": sorted(
            k for k in child_names if reference["children"].get(k) != copied["children"].get(k)
        ),
        "identical_sections": sorted(
            k for k in child_names if reference["children"].get(k) == copied["children"].get(k)
        ),
        "property_differences": differences,
        "fan_curve_identical": bool(reference["properties"].get("Fan Curve"))
        and reference["properties"].get("Fan Curve") == copied["properties"].get("Fan Curve"),
        "protected_files_preserved": all(
            hashlib.sha256(p.read_bytes()).hexdigest() == digest for p, digest in hashes.items()
        ),
        "other_existing_flags_preserved": {k: v for k, v in flags.items() if k != previous_path}
        == {p.FullPath: bool(p.IsModified) for p in executor.session.Parts if p != sim},
        "sim_copy": copy_receipt,
        "copied_results_reused": False,
        "solver_launched": False,
    }
    assert result["protected_files_preserved"]
    intent.write_text(json.dumps(result, indent=2))
    return result

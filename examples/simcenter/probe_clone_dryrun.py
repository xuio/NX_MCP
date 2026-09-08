"""Dry-run a bounded saved SIM/FEM/CAD clone; do not create native parts."""


def run(executor):
    return clone_saved_benchmark(executor, dry_run=True)


def clone_saved_benchmark(executor, *, dry_run, copy_associated_files=True):
    import hashlib

    import NXOpen.UF as uf_module

    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    root = executor.workspace.resolve("ui-benchmarks")
    source = root / "D-fine-k0-solve-20260908-r1/fine_k0_solve_r1.sim"
    base = root / "D-cavity-documents-20260908-r2"
    suffix = "dryrun" if dry_run else "native"
    if not copy_associated_files:
        suffix += "-no-associated"
    destination = root / f"D-independent-clone-{suffix}-20260908-r1"
    mapping = {
        source: destination / "independent_flow.sim",
        base / "benchmark_4ba7072a1d7a_mesh.fem": destination / "independent_mesh.fem",
        base / "benchmark_4ba7072a1d7a_geometry.prt": destination / "independent_geometry.prt",
    }
    for path in (*mapping, *mapping.values()):
        executor.workspace.resolve(str(path))
    hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in mapping}
    before = [(p.FullPath, bool(p.IsModified)) for p in executor.session.Parts]
    # Unique directory is a durable no-retry guard for this disposable fixture.
    destination.mkdir(exist_ok=False)
    log = destination / "clone-dryrun.log"
    clone = uf_module.UFSession.GetUFSession().Clone
    options = executor.session.Parts.LoadOptions
    original = options.ComponentLoadMethod
    started = False
    iterating = False
    result = {
        "dry_run": dry_run,
        "clone_performed": False,
        "mapping": {str(k): str(v) for k, v in mapping.items()},
    }
    try:
        options.ComponentLoadMethod = type(options).LoadMethod.AsSaved
        clone.Initialise(type(clone).OperationClass.CLONE_OPERATION)
        started = True
        status, code = clone.AddAssembly(str(source))
        if code or status.Failed or status.UserAbort or status.NParts:
            raise ValueError("Native dependency load did not pass")
        found = []
        clone.StartIteration()
        iterating = True
        for _ in range(32):
            name = clone.Iterate()
            if not name:
                iterating = False
                break
            found.append(executor.workspace.resolve(name))
        else:
            raise ValueError("Unbounded native clone inventory")
        if set(found) != set(mapping) or len(found) != len(mapping):
            raise ValueError("Native clone set differs from the explicit dependency set")
        clone.SetDefAction(type(clone).Action.CLONE)
        clone.SetDefAssocFileCopy(copy_associated_files)
        result["copy_associated_files"] = clone.AskDefAssocFileCopy()
        if result["copy_associated_files"] != copy_associated_files:
            raise ValueError("Native associated-file-copy readback differs")
        clone.SetDefNaming(type(clone).NamingTechnique.USER_NAME)
        for source_path, output_path in mapping.items():
            clone.SetNaming(
                str(source_path), type(clone).NamingTechnique.USER_NAME, str(output_path)
            )
        clone.SetLogfile(str(log))
        clone.SetDryrun(dry_run)
        failures = clone.InitNamingFailures()
        failures = clone.PerformClone(failures)
        result["naming_diagnostics"] = {
            name: str(getattr(failures, name))
            for name in dir(failures)
            if not name.startswith("_") and not callable(getattr(failures, name))
        }
        if failures.NFailures:
            raise ValueError("Native clone reported naming failures")
        result["state"] = "dry_run_returned" if dry_run else "clone_returned"
        result["clone_performed"] = not dry_run
    except Exception as error:
        result.update(
            state="failed",
            error_type=type(error).__name__,
            message=str(error),
            nx_code=getattr(error, "ErrorCode", None),
        )
    finally:
        try:
            if iterating:
                clone.StopIteration()
        finally:
            try:
                if started:
                    clone.Terminate()
            finally:
                options.ComponentLoadMethod = original
    result["load_method_restored"] = options.ComponentLoadMethod == original
    result["source_hashes"] = hashes
    result["source_files_preserved"] = all(
        hashlib.sha256(p.read_bytes()).hexdigest() == hashes[str(p)] for p in mapping
    )
    result["document_flags_preserved"] = before == [
        (p.FullPath, bool(p.IsModified)) for p in executor.session.Parts
    ]
    result["native_parts_created"] = [str(p) for p in mapping.values() if p.exists()]
    result["log"] = (
        log.read_text(encoding="utf-8-sig", errors="replace")[:20000] if log.exists() else None
    )
    assert (
        result["load_method_restored"]
        and result["source_files_preserved"]
        and result["document_flags_preserved"]
    )
    if dry_run:
        assert not result["native_parts_created"]
    elif result["state"] == "clone_returned":
        assert all(p.is_file() and p.stat().st_size > 0 for p in mapping.values())
        result["outputs"] = [
            {
                "path": str(p),
                "bytes": p.stat().st_size,
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            }
            for p in mapping.values()
        ]
        result["dependency_rebinding"] = "not_verified_until_reopen"
        if not copy_associated_files:
            actual_files = {p for p in destination.iterdir() if p.is_file()}
            assert actual_files == set(mapping.values()) | {log}
            result["only_native_parts_and_log_created"] = True
    return result

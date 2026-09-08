"""Enumerate the saved benchmark's native clone set; never perform a clone."""


def run(executor):
    import hashlib

    import NXOpen.UF as uf_module

    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    source = executor.workspace.resolve(
        r"D:\CAD\SIMCENTER_MCP_WORKSPACE\ui-benchmarks\D-fine-k0-solve-20260908-r1\fine_k0_solve_r1.sim"
    )
    before = [(p.FullPath, bool(p.IsModified)) for p in executor.session.Parts]
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    clone = uf_module.UFSession.GetUFSession().Clone
    options = executor.session.Parts.LoadOptions
    original_method = options.ComponentLoadMethod
    started = False
    iterating = False
    result = {
        "source": str(source),
        "source_revision": "saved file snapshot; loaded unsaved edits not included",
        "clone_performed": False,
        "parts": [],
    }
    try:
        options.ComponentLoadMethod = type(options).LoadMethod.AsSaved
        clone.Initialise(type(clone).OperationClass.CLONE_OPERATION)
        started = True
        status, code = clone.AddAssembly(str(source))
        result["add_return_code"] = code
        result["load_status"] = {
            "failed": bool(status.Failed),
            "user_abort": bool(status.UserAbort),
            "count": status.NParts,
            "file_names": list(status.FileNames),
            "codes": list(status.Statuses),
        }
        if code != 0 or status.Failed or status.UserAbort or status.NParts:
            raise ValueError("AddAssembly reported unresolved dependencies or load diagnostics")
        clone.StartIteration()
        iterating = True
        for _ in range(32):
            name = clone.Iterate()
            if not name:
                iterating = False
                break
            path = executor.workspace.resolve(name)
            result["parts"].append(str(path))
        else:
            raise ValueError("Clone inventory exceeds isolated benchmark limit")
        result["state"] = "inventory_returned"
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
                options.ComponentLoadMethod = original_method
    result["load_method_restored"] = options.ComponentLoadMethod == original_method
    result["source_file_preserved"] = hashlib.sha256(source.read_bytes()).hexdigest() == digest
    result["document_flags_preserved"] = before == [
        (p.FullPath, bool(p.IsModified)) for p in executor.session.Parts
    ]
    assert (
        result["source_file_preserved"]
        and result["document_flags_preserved"]
        and result["load_method_restored"]
    )
    return result

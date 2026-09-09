def run(executor):
    from nx_mcp.runtime import NXToolError
    from nx_mcp.simcenter import local_size, mesh_controls, remesh
    from nx_mcp.simcenter.mesh_plan import mesh_counts

    session = executor.session
    fem = session.Parts.BaseWork
    assert "L-face-size-20260909-r1" in fem.FullPath
    flags = [(p.FullPath, bool(p.IsModified)) for p in session.Parts]
    document = executor._reference(fem, "part", fem, "FEM")["id"]
    control = list(fem.BaseFEModel.MeshControls)[0]
    counts = mesh_counts(fem)
    result = {"document": fem.FullPath, "before_counts": counts}
    original = mesh_controls.inspect_control
    calls = []

    def fail_readback(*args):
        value = original(*args)
        calls.append(value["size_mm"])
        if len(calls) == 2:
            raise ValueError("Injected failure after native size edit")
        return value

    mesh_controls.inspect_control = fail_readback
    try:
        try:
            local_size.edit(executor, fem, control, 2.0)
        except NXToolError as error:
            result["edit_failure"] = {"code": error.code, "details": error.details}
        else:
            raise AssertionError("Expected edit failure")
    finally:
        mesh_controls.inspect_control = original
    result["edit_observed_sizes"] = calls
    assert result["edit_failure"]["details"]["mutation_outcome"] == "rolled_back"
    assert calls == [1.0, 2.0, 1.0]
    original = remesh.settings
    calls = []

    def fail_after_commit(*args):
        value = original(*args)
        calls.append(value)
        if len(calls) == 3:
            raise ValueError("Injected readback failure after first native mesh commit")
        return value

    remesh.settings = fail_after_commit
    try:
        try:
            remesh.regenerate(executor, fem)
        except NXToolError as error:
            result["remesh_failure"] = {"code": error.code, "details": error.details}
        else:
            raise AssertionError("Expected remesh failure")
    finally:
        remesh.settings = original
    assert result["remesh_failure"]["details"]["mutation_outcome"] == "rolled_back"
    result["settings_read_count"] = len(calls)
    result["counts_restored"] = counts == mesh_counts(fem)
    result["flags_restored"] = flags == [(p.FullPath, bool(p.IsModified)) for p in session.Parts]
    try:
        executor.objects.resolve(document, expected_kind="part")
    except NXToolError as error:
        result["old_document_rejection"] = error.code
    else:
        raise AssertionError("Old document ID remained valid")
    assert result["old_document_rejection"] == "NX_OBJECT_STALE"
    assert result["counts_restored"] and result["flags_restored"]
    result["passed"] = True
    result["solver_launched"] = False
    return result

def run(executor):
    import importlib
    import types

    from nx_mcp import hardened
    from nx_mcp.runtime import NXToolError
    from nx_mcp.simcenter import local_size, mesh_controls, native

    for module in [native, local_size, mesh_controls]:
        importlib.reload(module)
    method = types.MethodType(native.SimcenterMixin._sim_face_size, executor)
    executor._sim_face_size = method
    executor._handlers["nx_sim_face_size"] = method
    hardened.NON_MODEL.add("nx_sim_face_size")
    fem = executor.session.Parts.BaseWork
    assert "M-mixed-mesh-20260909-r1" in fem.FullPath, fem.FullPath
    document = executor._reference(fem, "part", fem, "FEM")["id"]
    face = executor._sim_faces(document)["faces"][0]["face"]["id"]
    before = {int(c.Tag) for c in fem.BaseFEModel.MeshControls}
    flags = [(p.FullPath, bool(p.IsModified)) for p in executor.session.Parts]
    original = mesh_controls.inspect_control
    reached = []

    def fail(*args):
        reached.append(len(list(fem.BaseFEModel.MeshControls)))
        raise ValueError("Injected failure after local size commit")

    try:
        mesh_controls.inspect_control = fail
        try:
            method(document, [face], 1.0)
        except NXToolError as error:
            assert error.details.get("mutation_outcome") == "rolled_back", error.details
            failure = {"code": error.code, "details": error.details}
        else:
            raise AssertionError("Expected post-commit failure")
    finally:
        mesh_controls.inspect_control = original
    after = {int(c.Tag) for c in fem.BaseFEModel.MeshControls}
    changed_flags = [(p.FullPath, bool(p.IsModified)) for p in executor.session.Parts]
    return {
        "registered": True,
        "rollback": failure,
        "post_commit_reached": bool(reached),
        "observed_counts": reached,
        "before_count": len(before),
        "after_count": len(after),
        "inventory_restored": before == after,
        "flags_restored": flags == changed_flags,
        "changed_flags": [(a, b) for a, b in zip(flags, changed_flags, strict=True) if a != b],
        "solver_launched": False,
    }

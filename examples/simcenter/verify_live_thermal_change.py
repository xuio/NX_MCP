"""Verify public frame handler with explicit readback and rollback."""


def run(executor):
    import importlib
    import types

    import nx_mcp.hardened as hardened
    import nx_mcp.simcenter.native as native
    import nx_mcp.simcenter.native_launch as native_launch
    import nx_mcp.simcenter.preparation as preparation
    import nx_mcp.simcenter.result_binding as result_binding
    import nx_mcp.simcenter.server as server
    import nx_mcp.simcenter.thermal_state as thermal_state
    from nx_mcp.runtime import NXToolError

    for module in (thermal_state, preparation, native_launch, result_binding):
        importlib.reload(module)
    importlib.reload(native)
    identity = types.MethodType(native.SimcenterMixin._sim_result_identity, executor)
    executor._sim_result_identity = identity
    executor._handlers["nx_sim_result_identity"] = identity
    importlib.reload(server)
    method = types.MethodType(native.SimcenterMixin._sim_material_frame, executor)
    executor._sim_material_frame = method
    executor._handlers["nx_sim_material_frame"] = method
    hardened.NON_MODEL.add("nx_sim_material_frame")
    session = executor.session
    flags = {p.FullPath: bool(p.IsModified) for p in session.Parts}
    work, display = session.Parts.BaseWork, session.Parts.BaseDisplay
    fem = next(p for p in session.Parts if p.FullPath.endswith("OrthoZR1_mesh.fem"))
    document = executor._reference(fem, "part", fem, "FEM")["id"]
    from nx_mcp.simcenter.thermal_state import capture_thermal_state, compare_thermal_state

    thermal_before = capture_thermal_state(fem, executor.nxopen)
    before = executor._sim_collectors(document)["collectors"][0]
    history, mark = len(executor._history), None
    args = [
        document,
        before["collector"]["id"],
        before["state_sha256"],
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
    ]
    try:
        try:
            method(*[args[0], args[1], "0" * 64, *args[3:]])
        except NXToolError as error:
            assert error.code == "NX_SIM_REVISION_MISMATCH"
        else:
            raise AssertionError("Stale state accepted")
        result = method(*args)
        mark = executor._history[-1]["mark"]
        after = result["collector_state"]
        thermal_after = capture_thermal_state(fem, executor.nxopen)
        comparison = compare_thermal_state(thermal_before, thermal_after)
        assert comparison["state"] == "changed"
        assert after["material"] == before["material"]
        assert after["orientation"]["stored_frame"]["axes_in_part_absolute"] == [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ]
        assert after["state_sha256"] != before["state_sha256"]
        return {
            "frame_edit": result,
            "thermal_state_comparison": comparison,
            "stale_state_rejected": True,
            "rolled_back_after_readback": True,
            "material_preserved": True,
        }
    finally:
        if mark is not None:
            session.UndoToMark(mark, None)
            session.DeleteUndoMark(mark, None)
            del executor._history[history:]
        assert (
            compare_thermal_state(thermal_before, capture_thermal_state(fem, executor.nxopen))[
                "state"
            ]
            == "matches"
        )
        assert executor._sim_collectors(document)["collectors"][0] == before
        _, status = session.Parts.SetDisplay(display, False, False)
        if status:
            status.Dispose()
        session.Parts.SetWork(work)
        assert flags == {p.FullPath: bool(p.IsModified) for p in session.Parts}

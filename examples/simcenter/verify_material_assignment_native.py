"""Verify explicit solid assignment, state conflict, and rollback in isolated FEM."""


def run(executor):
    import importlib
    import types

    import nx_mcp.hardened as hardened
    import nx_mcp.simcenter.native as native
    import nx_mcp.simcenter.server as server
    from nx_mcp.runtime import NXToolError
    from nx_mcp.simcenter.directional_material import create_orthotropic

    importlib.reload(native)
    importlib.reload(server)
    method = types.MethodType(native.SimcenterMixin._sim_assign_material, executor)
    executor._sim_assign_material = method
    executor._handlers["nx_sim_assign_material"] = method
    hardened.NON_MODEL.add("nx_sim_assign_material")
    session = executor.session
    flags = {p.FullPath: bool(p.IsModified) for p in session.Parts}
    work, display = session.Parts.BaseWork, session.Parts.BaseDisplay
    fem = next(p for p in session.Parts if p.FullPath.endswith("OrthoZR1_mesh.fem"))
    document = executor._reference(fem, "part", fem, "FEM")["id"]
    before = executor._sim_collectors(document)["collectors"][0]
    history = len(executor._history)
    material_mark = assignment_mark = None
    trace = {"stage": "create"}
    try:
        material, _, material_mark = create_orthotropic(
            session,
            executor.nxopen,
            fem,
            conductivities=[11, 6, 0.5],
            density=1900,
            heat_capacity=900,
            name="MCP_ASSIGNMENT_TEMP_R1",
            provenance="Temporary native test",
        )
        trace["stage"] = "stale_state_check"
        material_id = executor._reference(material, "material", fem, material.Name)["id"]
        try:
            method(document, before["collector"]["id"], material_id, "0" * 64)
        except NXToolError as error:
            assert error.code == "NX_SIM_REVISION_MISMATCH"
        else:
            raise AssertionError("Stale state was accepted")
        trace["stage"] = "assign"
        result = method(document, before["collector"]["id"], material_id, before["state_sha256"])
        trace["result"] = result
        trace["stage"] = "assert_readback"
        assignment_mark = executor._history[-1]["mark"]
        after = result["collector_state"]
        assert after["material"]["id"] == material_id
        assert after["orientation"] == before["orientation"]
        assert after["state_sha256"] != before["state_sha256"]
        return {
            "assignment": result,
            "stale_state_rejected": True,
            "orientation_preserved": True,
            "rolled_back_after_readback": True,
            "test_material_removed": True,
        }
    except Exception:
        import traceback

        trace["traceback"] = traceback.format_exc()
        raise
    finally:
        import json
        from pathlib import Path

        Path(r"Z:\nx-mcp-integration\simcenter-discovery\assignment-test-trace.json").write_text(
            json.dumps(trace, indent=2)
        )
        if assignment_mark is not None:
            session.UndoToMark(assignment_mark, None)
            session.DeleteUndoMark(assignment_mark, None)
            del executor._history[history:]
        if material_mark is not None:
            session.UndoToMark(material_mark, None)
            session.DeleteUndoMark(material_mark, None)
        assert executor._sim_collectors(document)["collectors"][0] == before
        assert not any(
            m.Name == "MCP_ASSIGNMENT_TEMP_R1" for m in fem.MaterialManager.PhysicalMaterials
        )
        _, status = session.Parts.SetDisplay(display, False, False)
        if status:
            status.Dispose()
        session.Parts.SetWork(work)
        assert flags == {p.FullPath: bool(p.IsModified) for p in session.Parts}

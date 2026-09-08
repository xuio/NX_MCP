"""Verify live load-change detection and restored fingerprint after rollback."""


def run(executor):
    import importlib

    from nx_mcp.simcenter import boundary_state, thermal_state
    from nx_mcp.simcenter.distributed_heat import create_distributed_heat
    from nx_mcp.simcenter.selections import face_inventory

    importlib.reload(boundary_state)
    importlib.reload(thermal_state)
    s = executor.session
    old_work, old_display = s.Parts.BaseWork, s.Parts.BaseDisplay
    sim = next(p for p in s.Parts if p.FullPath.endswith("volume_solve_r1.sim"))
    try:
        executor._sim_activate(executor._reference(sim, "part", sim, "SIM")["id"])
        before = thermal_state.capture_analysis_thermal_state(sim)
        assert before["sha256"], before["errors"]
        flags = [(p.FullPath, bool(p.IsModified)) for p in s.Parts]
        face = face_inventory(s, sim)["rows"][0]["face"]
        mark = s.SetUndoMark(
            executor.nxopen.Session.MarkVisibility.Visible, "Boundary fingerprint acceptance"
        )
        try:
            create_distributed_heat(
                s,
                sim,
                [face],
                kind="surface_flux",
                value=100,
                name="Fingerprint heat probe",
                provenance="Isolated transient test mutation",
                overlap_policy="allow_additive",
            )
            changed = thermal_state.capture_analysis_thermal_state(sim)
            comparison = thermal_state.compare_thermal_state(before, changed)
            assert comparison["state"] == "changed"
        finally:
            s.UndoToMark(mark, None)
            s.DeleteUndoMark(mark, None)
        restored = thermal_state.capture_analysis_thermal_state(sim)
        assert restored["sha256"] == before["sha256"]
        assert flags == [(p.FullPath, bool(p.IsModified)) for p in s.Parts]
        return {
            "before": before,
            "changed": changed,
            "comparison": comparison,
            "restored_sha256": restored["sha256"],
            "rollback_verified": True,
            "full_model_freshness": "not_verified",
        }
    finally:
        _, status = s.Parts.SetDisplay(old_display, False, False)
        if status is not None:
            status.Dispose()
        s.Parts.SetWork(old_work)

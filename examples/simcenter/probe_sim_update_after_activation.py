def run(executor):
    import json
    import time
    from pathlib import Path
    from types import SimpleNamespace

    from nx_mcp.simcenter.mesh_plan import mesh_counts
    from nx_mcp.simcenter.property_values import preserved_getter_state
    from nx_mcp.simcenter.solver_guard import require_solver_idle
    from nx_mcp.simcenter.thermal_state import capture_analysis_thermal_state, compare_thermal_state

    require_solver_idle()
    nx, session = executor.nxopen, executor.session
    sim = next(
        p
        for p in session.Parts
        if type(p).__name__ == "SimPart" and "U-sim-update-20260909-r1" in p.FullPath
    )
    fem = sim.FemPart
    assert session.Parts.BaseWork == fem
    flags = [(p.FullPath, bool(p.IsModified)) for p in session.Parts]
    output = Path(r"Z:\nx-mcp-integration\simcenter-discovery\sim-update-r2-progress.json")
    result = {"document": sim.FullPath, "solver_launched": False, "fem_before": mesh_counts(fem)}

    def record():
        output.write_text(json.dumps(result, indent=2))

    def state():
        with preserved_getter_state(nx):
            return capture_analysis_thermal_state(sim)

    switchmark = session.SetUndoMark(
        nx.Session.MarkVisibility.Invisible, "NX MCP activation mark probe"
    )
    _, status = session.Parts.SetDisplay(sim, False, False)
    if status:
        status.Dispose()
    session.Parts.SetWork(sim)
    result["mark_survived_activation"] = session.DoesUndoMarkExist(switchmark, None)
    if result["mark_survived_activation"]:
        session.DeleteUndoMark(switchmark, None)
    record()
    result["after_activation"] = mesh_counts(SimpleNamespace(BaseFEModel=sim.Simulation.Femodel))
    initial = state()
    result["before_update_state"] = initial
    record()
    mark = session.SetUndoMark(
        nx.Session.MarkVisibility.Visible, "NX MCP explicit SIM update probe"
    )
    start = time.monotonic()
    try:
        result["update_available"] = callable(getattr(sim.Simulation, "UpdateFemodel", None))
        record()
        sim.Simulation.UpdateFemodel()
        result["update_returned"] = True
        result["mark_survived_update"] = session.DoesUndoMarkExist(mark, None)
        record()
        result["after_update"] = mesh_counts(SimpleNamespace(BaseFEModel=sim.Simulation.Femodel))
        current = state()
        result["after_update_state"] = current
        result["assignment_comparison"] = compare_thermal_state(initial, current)
        result["passed"] = (
            result["after_update"] == result["fem_before"]
            and result["assignment_comparison"]["state"] == "matches"
        )
        record()
    except Exception as error:
        result["passed"] = False
        result["error"] = {
            "type": type(error).__name__,
            "message": str(error),
            "nx_code": getattr(error, "ErrorCode", None),
        }
        record()
    finally:
        result["mark_available_for_recovery"] = session.DoesUndoMarkExist(mark, None)
        if result["mark_available_for_recovery"]:
            try:
                session.UndoToMark(mark, None)
                session.DeleteUndoMark(mark, None)
                result["update_undone"] = True
            except Exception as error:
                result["recovery_error"] = str(error)
        else:
            result["recovery_limitation"] = (
                "Explicit update invalidated the probe checkpoint; no undo attempted"
            )
        executor.objects.invalidate_part(executor._part_id(fem))
        executor.objects.invalidate_part(executor._part_id(sim))
    result["elapsed_seconds"] = time.monotonic() - start
    result["flags_unchanged"] = flags == [(p.FullPath, bool(p.IsModified)) for p in session.Parts]
    result["fem_after_recovery"] = mesh_counts(fem)
    sim.ModelingViews.WorkView.Fit()
    sim.ModelingViews.WorkView.UpdateDisplay()
    record()
    return result

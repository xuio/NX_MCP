"""Known failing isolated-fixture reproducer; leaves the test mesh edited.

Demonstrates that a checkpoint created before document activation is lost.
Use inspect_sim_update_recovery.py and the staged activation probe afterward.
Never use this as an ordinary mesh workflow or on a production model.
"""


def run(executor):
    import time
    from types import SimpleNamespace

    from nx_mcp.simcenter.mesh_plan import mesh_counts
    from nx_mcp.simcenter.property_values import preserved_getter_state
    from nx_mcp.simcenter.solver_guard import require_solver_idle
    from nx_mcp.simcenter.thermal_state import capture_analysis_thermal_state, compare_thermal_state

    require_solver_idle()
    nx, session = executor.nxopen, executor.session
    sim = session.Parts.BaseWork
    assert type(sim).__name__ == "SimPart" and "U-sim-update-20260909-r1" in sim.FullPath
    fem = sim.FemPart
    flags = [(p.FullPath, bool(p.IsModified)) for p in session.Parts]

    def counts():
        return {
            "fem": mesh_counts(fem),
            "sim_occurrence": mesh_counts(SimpleNamespace(BaseFEModel=sim.Simulation.Femodel)),
        }

    def state():
        with preserved_getter_state(nx):
            return capture_analysis_thermal_state(sim)

    initial = state()
    before = counts()
    result = {
        "document": sim.FullPath,
        "hypothesis": "SimSimulation.UpdateFemodel updates the associated occurrence after tetra remesh while retaining material/boundary assignments",
        "before_counts": before,
        "before_state": initial,
        "solver_launched": False,
    }
    mark = session.SetUndoMark(nx.Session.MarkVisibility.Visible, "NX MCP bounded SIM update probe")
    start = time.monotonic()
    try:
        manager = fem.BaseFEModel.MeshManager
        meshes = list(manager.GetMeshes())
        assert len(meshes) == 1
        _, status = session.Parts.SetDisplay(fem, False, False)
        if status:
            status.Dispose()
        session.Parts.SetWork(fem)
        builder = manager.CreateMesh3dTetBuilder(meshes[0])
        try:
            size, unit = builder.PropertyTable.GetBaseScalarWithDataPropertyValue(
                "quad mesh overall edge size"
            )
            assert size == 5 and unit.Name == "MilliMeter"
            builder.PropertyTable.SetBaseScalarWithDataPropertyValue(
                "quad mesh overall edge size", 3.0, unit
            )
            builder.AutoSizeOption = False
            builder.CommitMesh()
        finally:
            builder.Destroy()
        result["after_remesh_before_activation"] = counts()
        result["fem_update_pending"] = fem.BaseFEModel.AskUpdatePending()
        _, status = session.Parts.SetDisplay(sim, False, False)
        if status:
            status.Dispose()
        session.Parts.SetWork(sim)
        result["before_explicit_update"] = counts()
        result["update_method_available"] = callable(getattr(sim.Simulation, "UpdateFemodel", None))
        sim.Simulation.UpdateFemodel()
        result["after_update"] = counts()
        current = state()
        result["after_state"] = current
        result["assignment_comparison"] = compare_thermal_state(initial, current)
        assert result["after_update"]["fem"] == result["after_update"]["sim_occurrence"]
        assert result["after_update"]["fem"]["elements"] > before["fem"]["elements"]
        assert result["assignment_comparison"]["state"] == "matches"
        result["passed"] = True
    except Exception as error:
        result["passed"] = False
        result["error"] = {
            "type": type(error).__name__,
            "message": str(error),
            "nx_code": getattr(error, "ErrorCode", None),
        }
    finally:
        session.UndoToMark(mark, None)
        session.DeleteUndoMark(mark, None)
        _, status = session.Parts.SetDisplay(sim, False, False)
        if status:
            status.Dispose()
        session.Parts.SetWork(sim)
        executor.objects.invalidate_part(executor._part_id(fem))
        executor.objects.invalidate_part(executor._part_id(sim))
    result["elapsed_seconds"] = time.monotonic() - start
    result["counts_restored"] = counts() == before
    result["state_restored"] = compare_thermal_state(initial, state())
    result["flags_restored"] = flags == [(p.FullPath, bool(p.IsModified)) for p in session.Parts]
    sim.ModelingViews.WorkView.Fit()
    sim.ModelingViews.WorkView.UpdateDisplay()
    return result

"""Native schedule rollback, target persistence and constant-load regression; no solve."""


def run(executor):
    import json
    from pathlib import Path

    import NXOpen.UF as uf

    from nx_mcp.runtime import NXToolError
    from nx_mcp.simcenter import heat_loads, heat_schedule, scalar_tables
    from nx_mcp.simcenter.solver_guard import require_solver_idle
    from nx_mcp.simcenter.time_controls import configure_transient_steps

    require_solver_idle()
    session = executor.session
    sim = session.Parts.BaseWork
    shared = Path(r"Z:\nx-mcp-integration\simcenter-discovery")
    previous = json.loads((shared / "heat-schedule-public.json").read_text())
    assert previous["passed"] and sim.FullPath == previous["path"]
    load = next(b for b in sim.Simulation.Loads if b.Name == "MCP_PUBLIC_HEAT")
    _, members = load.TargetSetManager.GetTargetSetMembers(0)
    component = list(sim.ComponentAssembly.RootComponent.GetChildren())[0]
    body = list(sim.FemPart.Bodies)[0]
    assert len(list(sim.FemPart.Bodies)) == len(members) == 1
    assert members[0].Obj.Tag == component.FindOccurrence(body).Tag
    sf = uf.UFSession.GetUFSession().Sf
    box = list(sf.BodyAskBoundingBox(body.Tag))
    assert all(abs(a - b) < 1e-8 for a, b in zip(box, [0, 0, 0, 10, 10, 10], strict=True)), box
    persistence = {"path": sim.FullPath, "target_matches_reopened_fem_body": True, "bounds_mm": box}
    unrelated = {p.FullPath: bool(p.IsModified) for p in session.Parts}
    fixture = executor._sim_create_benchmark(
        "ui-benchmarks/T-heat-recovery-20260909-r1",
        length_mm=10,
        width_mm=10,
        height_mm=10,
        block_origins_mm=[[0, 0, 0], [20, 0, 0]],
    )
    sim = session.Parts.BaseWork
    configure_transient_steps(
        session, sim, [0, 10, 20], max_temperature_change_k=1, min_time_step_s=0.01
    )
    field = scalar_tables.create(
        session,
        sim,
        {
            "name": "MCP_RECOVERY_POWER",
            "axis": "time",
            "quantity": "power",
            "samples": [[0, 0], [10, 1], [20, 0]],
            "provenance": "Isolated recovery fixture",
        },
    ).pop("table")
    sid = executor._reference(sim, "part", sim, "SIM")["id"]
    executor._sim_save(sid)
    comp = list(sim.ComponentAssembly.RootComponent.GetChildren())[0]
    bodies = sorted(sim.FemPart.Bodies, key=lambda b: sf.BodyAskBoundingBox(b.Tag)[0])
    occurrences = [comp.FindOccurrence(b) for b in bodies]

    def snapshot():
        return {
            "loads": sorted(int(b.Tag) for b in sim.Simulation.Loads),
            "expressions": sorted(int(e.Tag) for e in sim.Expressions),
            "fields": sorted(int(f.Tag) for f in sim.FieldManager.Fields),
            "membership": sorted(int(b.Tag) for b in sim.Simulation.ActiveSolution.GetBcs()),
            "flags": {p.FullPath: bool(p.IsModified) for p in session.Parts},
        }

    before = snapshot()
    original = heat_schedule.verify_committed

    injections = []

    def fail(*args):
        injections.append(True)
        raise NXToolError("NX_SIM_READBACK_MISMATCH", "Injected schedule post-commit failure")

    try:
        heat_schedule.verify_committed = fail
        try:
            heat_loads.create_body_power(
                session,
                sim,
                occurrences[0],
                0,
                "MCP_RECOVERY_HEAT",
                "Failure injection",
                schedule_field=field,
                schedule_scale=2,
            )
        except NXToolError as error:
            assert error.details["mutation_outcome"] == "rolled_back", error.details
            recovery = {"code": error.code, "details": error.details}
        else:
            raise AssertionError("Expected injected failure")
    finally:
        heat_schedule.verify_committed = original
    assert injections == [True], "Expected post-commit verifier was not reached"
    assert snapshot() == before
    scheduled = heat_loads.create_body_power(
        session,
        sim,
        occurrences[0],
        0,
        "MCP_RECOVERY_HEAT",
        "Verified retry",
        schedule_field=field,
        schedule_scale=2,
    )
    assert scheduled["schedule"]["samples_w"] == [[0, 0], [10, 2], [20, 0]]
    constant = heat_loads.create_body_power(
        session, sim, occurrences[1], 3, "MCP_CONSTANT_HEAT", "Constant regression"
    )
    assert constant["power_w"] == 3 and "schedule" not in constant
    executor._sim_save(sid)
    assert all(
        {p.FullPath: bool(p.IsModified) for p in session.Parts}[k] == v
        for k, v in unrelated.items()
    )
    session.ListingWindow.CloseWindow()
    sim.ModelingViews.WorkView.Fit()
    sim.ModelingViews.WorkView.UpdateDisplay()
    result = {
        "fixture": fixture,
        "document": sid,
        "path": sim.FullPath,
        "persistence": persistence,
        "injected_failure": recovery,
        "snapshot_restored": True,
        "successful_retry": True,
        "constant_power_regression_w": constant["power_w"],
        "unrelated_flags_preserved": True,
        "solver_launched": False,
    }
    (shared / "heat-schedule-recovery.json").write_text(json.dumps(result, indent=2))
    return result

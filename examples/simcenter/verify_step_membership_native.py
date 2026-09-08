"""Native step membership/order/persistence fixture; no mesh or solver execution."""


def run(executor):
    import json
    import shutil
    from pathlib import Path

    import NXOpen.UF as uf

    from nx_mcp.simcenter.boundary_state import capture_effective_membership
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    root = executor.workspace.resolve("ui-benchmarks/F2-step-membership-20260909-r1")
    if root.exists():
        raise ValueError("Inspect retained step-membership fixture before retry")
    root.mkdir()
    flags = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    source = executor.workspace.resolve(
        "ui-benchmarks/volume-numerical-solve-20260908-r1/volume_solve_r1.sim"
    )
    path = root / "f2_step_membership_r1.sim"
    shutil.copy2(source, path)
    executor._sim_open(str(path))
    sim = executor.session.Parts.BaseWork
    solution = sim.Simulation.ActiveSolution
    assert solution.StepCount == 1
    native = uf.UFSession.GetUFSession()
    descriptor = native.Sf.SolutionAskDescriptorNx(solution.Tag)
    allowed = [
        native.Sfl.StepDescriptorAskNameNx(
            native.Sfl.SolutionAskNthAllowableStepDescriptorNx(descriptor, i)
        )
        for i in range(solution.AllowedStepTypeCount)
    ]
    assert allowed.count("Step - Thermal") == 1
    first = solution.GetStepByIndex(0)
    second = solution.CreateStep(allowed.index("Step - Thermal"), False, "Membership phase two")
    loads = list(sim.Simulation.Loads)
    assert len(loads) == 1
    load = loads[0]
    if load in list(solution.GetBcs()):
        solution.RemoveBc(load)
    for step in (first, second):
        if load in list(step.GetBcs()):
            step.RemoveBc(load)
    first.AddBc(load)
    before = capture_effective_membership(sim)
    assert before["comparison_verified"]
    first.RemoveBc(load)
    second.AddBc(load)
    moved = capture_effective_membership(sim)
    assert moved["comparison_verified"] and moved["sha256"] != before["sha256"]
    assert load not in list(first.GetBcs()) and load in list(second.GetBcs())
    assert list(sim.Simulation.Loads) == loads
    solution.MoveStep(second, solution.StepPosition.Before, first)
    ordered = capture_effective_membership(sim)
    assert ordered["comparison_verified"] and ordered["sha256"] != moved["sha256"]
    assert solution.GetStepByIndex(0) == second
    reference = executor._reference(sim, "part", sim, "SIM")["id"]
    executor._sim_save(reference)
    executor._sim_close(reference)
    executor._sim_open(str(path))
    reopened = executor.session.Parts.BaseWork
    after = capture_effective_membership(reopened)
    assert after == ordered
    current = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts}
    assert all(current.get(path) == value for path, value in flags.items())
    result = {
        "passed": True,
        "before": before,
        "moved": moved,
        "ordered": ordered,
        "reopened": after,
        "document": executor._reference(reopened, "part", reopened, "SIM")["id"],
        "document_load_inventory_preserved": True,
        "unrelated_modified_flags_preserved": True,
        "solver_launched": False,
    }
    (root / "verification.json").write_text(json.dumps(result, indent=2))
    Path(r"Z:\nx-mcp-integration\simcenter-discovery\step-membership-native.json").write_text(
        json.dumps(result, indent=2)
    )
    return result

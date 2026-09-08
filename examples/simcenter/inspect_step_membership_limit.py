"""Bounded native step-BC prerequisite comparison; preserve failed/no-op evidence."""


def run(executor):
    import json
    from pathlib import Path

    from nx_mcp.simcenter.boundary_state import capture_effective_membership
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    sim = executor.session.Parts.BaseWork
    assert sim.FullPath.endswith("f2_step_membership_r1.sim")
    flags = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts if p != sim}
    solution = sim.Simulation.ActiveSolution
    assert solution.StepCount == 2
    first, second = [solution.GetStepByIndex(i) for i in range(2)]
    load = next(iter(sim.Simulation.Loads))
    solution.AddBc(load)
    assert load in list(solution.GetBcs()), "Global membership did not commit"
    before = capture_effective_membership(sim)
    first.AddBc(load)
    in_first = load in list(first.GetBcs())
    first.RemoveBc(load)
    second.AddBc(load)
    in_second = load in list(second.GetBcs())
    attempted = capture_effective_membership(sim)
    # Preserve native outcome, not a fabricated pass for step-level assignment.
    second.RemoveBc(load)
    before_order = capture_effective_membership(sim)
    solution.MoveStep(second, solution.StepPosition.Before, first)
    after_order = capture_effective_membership(sim)
    assert solution.GetStepByIndex(0) == second, "Step order did not commit"
    assert before_order["sha256"] != after_order["sha256"]
    ref = executor._reference(sim, "part", sim, "SIM")["id"]
    path = sim.FullPath
    executor._sim_save(ref)
    executor._sim_close(ref)
    executor._sim_open(path)
    reopened = executor.session.Parts.BaseWork
    persisted = capture_effective_membership(reopened)
    assert persisted == after_order
    assert flags == {
        p.FullPath: bool(p.IsModified) for p in executor.session.Parts if p != reopened
    }
    result = {
        "step_order_and_reopen_passed": True,
        "step_bc_assignment_passed": in_first and in_second,
        "first_add_committed": in_first,
        "second_add_committed": in_second,
        "global_membership_present_during_attempt": True,
        "before": before,
        "attempted": attempted,
        "ordered": after_order,
        "document": executor._reference(reopened, "part", reopened, "SIM")["id"],
        "unrelated_modified_flags_preserved": True,
        "solver_launched": False,
    }
    Path(r"Z:\nx-mcp-integration\simcenter-discovery\step-membership-limit.json").write_text(
        json.dumps(result, indent=2)
    )
    return result

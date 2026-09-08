"""Native add/remove membership audit on an isolated SIM copy, without solving."""


def run(executor):
    import importlib
    import json

    import NXOpen as nx

    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    module = importlib.reload(importlib.import_module("nx_mcp.simcenter.boundary_state"))
    root = executor.workspace.resolve("ui-benchmarks/F2-membership-audit-20260908-r1")
    if root.exists():
        raise ValueError("Inspect retained membership audit before retry")
    source = executor.workspace.resolve(
        "ui-benchmarks/E-finned-tight-20260908-r1/finned_tight_r1.sim"
    )
    executor._sim_open(str(source))
    sim = executor.session.Parts.BaseWork
    executor._sim_save_as(
        executor._reference(sim, "part", sim, "SIM")["id"], str(root / "membership.sim")
    )
    solution = sim.Simulation.ActiveSolution
    loads = list(sim.Simulation.Loads)
    if len(loads) != 1 or loads[0] not in list(solution.GetBcs()):
        raise ValueError("Expected one selected heat load")
    original = module.capture_effective_membership(sim)
    if not original["comparison_verified"]:
        raise ValueError("Original membership unverified")
    mark = executor.session.SetUndoMark(
        nx.Session.MarkVisibility.Visible, "MCP effective membership audit"
    )
    try:
        solution.RemoveBc(loads[0])
        removed = module.capture_effective_membership(sim)
        if list(sim.Simulation.Loads) != loads:
            raise ValueError("Removing membership unexpectedly changed document inventory")
        if not removed["comparison_verified"] or removed["sha256"] == original["sha256"]:
            raise ValueError("Membership removal not detected")
        solution.AddBc(loads[0])
        restored = module.capture_effective_membership(sim)
        if restored != original:
            raise ValueError("Membership add readback differs")
    finally:
        executor.session.UndoToMark(mark, None)
    if module.capture_effective_membership(sim) != original:
        raise ValueError("Native audit rollback differs")
    result = {
        "before": original,
        "removed": removed,
        "restored": restored,
        "document_inventory_unchanged": True,
        "audit_edits_rolled_back": True,
        "solver_launched": False,
        "scope": "Native direct membership; no complete boundary-property or public MCP acceptance claim",
    }
    (root / "verification.json").write_text(json.dumps(result, indent=2))
    return result

"""Save/reopen the isolated membership fixture and reject its old live reference."""


def run(executor):
    import json
    from pathlib import Path

    from nx_mcp.runtime import NXToolError
    from nx_mcp.simcenter.boundary_state import capture_effective_membership
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    sim = executor.session.Parts.BaseWork
    path = Path(sim.FullPath)
    if "F2-membership-audit-20260908-r1" not in str(path):
        raise ValueError("Requires the isolated membership fixture")
    receipt = path.parent / "reopen-verification.json"
    if receipt.exists():
        raise ValueError("Inspect existing lifecycle receipt")
    before = capture_effective_membership(sim)
    flags = {p.FullPath: bool(p.IsModified) for p in executor.session.Parts if p != sim}
    ref = executor._reference(sim, "part", sim, "SIM")["id"]
    executor._sim_save(ref)
    executor._sim_close(ref)
    try:
        executor.objects.resolve(ref, expected_kind="part")
    except NXToolError as error:
        stale_error = error.code
    else:
        raise ValueError("Closed document reference unexpectedly resolves")
    executor._sim_open(str(path))
    reopened = executor.session.Parts.BaseWork
    after = capture_effective_membership(reopened)
    if after != before:
        raise ValueError("Membership changed after reopen")
    if flags != {p.FullPath: bool(p.IsModified) for p in executor.session.Parts if p != reopened}:
        raise ValueError("Unrelated document flags changed")
    result = {
        "before": before,
        "after": after,
        "membership_preserved": True,
        "stale_reference_error": stale_error,
        "unrelated_modified_flags_preserved": True,
        "solver_launched": False,
    }
    receipt.write_text(json.dumps(result, indent=2))
    return result

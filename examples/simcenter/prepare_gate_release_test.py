"""Claim a test launch gate for an already verified terminal job; never solve."""


def run(executor):
    from nx_mcp.simcenter.jobs import JobStore
    from nx_mcp.simcenter.launch_gate import claim_launch_gate
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    store = JobStore(executor.workspace)
    job = store.inspect("public-prepared-flow-01")
    if job["state"] != "solver_exited" or job["record"]["evidence"].get("observer_adapter") != 1:
        raise ValueError("Expected verified terminal flow fixture")
    require_solver_idle()
    flags = [(part.FullPath, bool(part.IsModified)) for part in executor.session.Parts]
    gate = claim_launch_gate(store, "public-prepared-flow-01")
    assert flags == [(part.FullPath, bool(part.IsModified)) for part in executor.session.Parts]
    return {"gate": gate, "scope": "Post-run gate fixture setup; not a new solver launch", "document_flags_preserved": True}

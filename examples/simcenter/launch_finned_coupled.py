"""Launch exactly the inspected prepared finned job; never repeat a long solve."""


def run(executor):
    import json

    from nx_mcp.simcenter.solver_guard import require_solver_idle

    receipt = executor.workspace.resolve("ui-benchmarks/E-finned-launch-r2.json")
    if receipt.exists():
        return {"existing_receipt": json.loads(receipt.read_text()), "solver_relaunched": False}
    require_solver_idle()
    sim = executor.session.Parts.BaseWork
    if "E-finned-run-20260908-r2" not in sim.FullPath:
        raise ValueError("Activate the exact inspected prepared SIM")
    data = {
        "job_id": "coupled-finned-baseline-r2",
        "acceptance": False,
        "stage": "launch_intent",
        "scope": "Finned coupled baseline; global reference explicitly 0 C, external temperatures 20 C; general ambient export limitation persists",
    }
    receipt.write_text(json.dumps(data, indent=2))
    data["launch"] = executor._sim_launch(
        executor._reference(sim, "part", sim, "SIM")["id"], data["job_id"]
    )
    data["stage"] = "launch_returned"
    receipt.write_text(json.dumps(data, indent=2))
    return data

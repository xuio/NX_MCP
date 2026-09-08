"""Inspect fields of the retained external-temperature coupled diagnostic; no solve."""


def run(executor):
    import time
    from nx_mcp.simcenter.results import iteration_inventory, temperature_extrema
    from nx_mcp.simcenter.flow_results import pressure_extrema
    from nx_mcp.simcenter.solver_guard import require_solver_idle

    require_solver_idle()
    sim = executor.session.Parts.BaseWork
    if "E-external-diagnostic-20260908-r1" not in sim.FullPath:
        raise ValueError("Activate the retained external diagnostic SIM")
    before = bool(sim.IsModified)
    started = time.monotonic()
    results = {}
    for name, reader in [
        ("inventory", iteration_inventory),
        ("temperature", temperature_extrema),
        ("pressure", pressure_extrema),
    ]:
        try:
            results[name] = reader(executor.session, sim)
        except Exception as error:
            results[name] = {
                "error": type(error).__name__,
                "message": str(error),
                "nx_code": getattr(error, "ErrorCode", None),
            }
    return {
        "document": sim.FullPath,
        "results": results,
        "modified_before": before,
        "modified_after": bool(sim.IsModified),
        "elapsed_seconds": time.monotonic() - started,
        "solver_launched": False,
        "numerical_acceptance": False,
    }
